# -*- coding: utf-8 -*-
"""
Custom report controller for pallet labels.
Uses wkhtmltoimage for HTML to image rendering.
Creates PDF with exact image dimensions for true roll printing.
"""

import base64
import io
import logging
import os
import subprocess
import tempfile

from odoo import http
from odoo.http import request, content_disposition

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from PIL import Image
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    sync_playwright = None

_logger = logging.getLogger(__name__)


class PalletLabelController(http.Controller):
    
    @http.route('/report/pallet_label/<string:pallet_ids>', type='http', auth='user')
    def print_pallet_label(self, pallet_ids, **kwargs):
        """
        Custom endpoint for pallet label printing.
        Renders each pallet as HTML -> Image (via Playwright) -> PDF with exact height.
        """
        if not REPORTLAB_AVAILABLE:
            _logger.warning("reportlab not available, falling back to standard PDF")
            return self._fallback_to_standard_report(pallet_ids)
        
        try:
            # Parse pallet IDs
            ids = [int(x) for x in pallet_ids.split(',') if x.strip().isdigit()]
            if not ids:
                return request.not_found()
            
            pallets = request.env['sale.order.pallet'].browse(ids).exists()
            if not pallets:
                return request.not_found()
            
            # Generate PDF with image-based pages
            pdf_content = self._generate_image_based_pdf(pallets)
            
            if not pdf_content:
                return self._fallback_to_standard_report(pallet_ids)
            
            # Build filename
            if len(pallets) == 1:
                filename = f"pallet_label_{pallets[0].name}.pdf"
            else:
                filename = f"pallet_labels_{pallets[0].order_id.name}.pdf"
            
            return request.make_response(
                pdf_content,
                headers=[
                    ('Content-Type', 'application/pdf'),
                    ('Content-Disposition', content_disposition(filename)),
                ]
            )
        except Exception as e:
            _logger.exception("Error generating pallet label PDF: %s", e)
            return self._fallback_to_standard_report(pallet_ids)
    
    def _generate_image_based_pdf(self, pallets):
        """
        Generate PDF where each page is an image of the rendered label.
        Page height matches image height for true roll printing.
        """
        images = []
        
        for pallet in pallets:
            img_bytes = self._render_pallet_to_image(pallet)
            if img_bytes:
                images.append(img_bytes)
        
        if not images:
            return None
        
        return self._create_pdf_from_images(images)
    
    def _render_pallet_to_image(self, pallet):
        """
        Render a single pallet's label HTML to PNG image.
        Uses Playwright for high-quality rendering if available, falls back to wkhtmltoimage.
        """
        try:
            # Render the QWeb template to HTML
            html = self._render_label_html(pallet)
            
            if not html:
                return None
            
            # Try Playwright first for best quality
            if PLAYWRIGHT_AVAILABLE:
                try:
                    return self._render_with_playwright(html)
                except Exception as e:
                    _logger.warning("Playwright rendering failed, trying wkhtmltoimage: %s", e)
            
            # Fallback to wkhtmltoimage
            return self._render_with_wkhtmltoimage(html)
                    
        except Exception as e:
            _logger.exception("Error rendering pallet to image: %s", e)
            return None
    
    def _render_with_playwright(self, html):
        """
        Render HTML to PNG using Playwright (headless Chromium).
        Sync API - works well in Odoo's synchronous request handling.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            try:
                # Start with small viewport to avoid min-height issues
                page = browser.new_page(
                    viewport={'width': 400, 'height': 100},
                    device_scale_factor=2,  # 2x for high DPI quality
                )
                
                # Set content
                page.set_content(html, wait_until='networkidle')
                
                # Wait for fonts to load
                page.wait_for_timeout(300)
                
                # Get actual content height from the pallet-label div
                content_height = page.evaluate('''() => {
                    const label = document.querySelector('.pallet-label');
                    if (label) {
                        return label.offsetHeight + 20;  // Add small padding
                    }
                    return document.body.scrollHeight;
                }''')
                
                # Resize viewport to actual content
                page.set_viewport_size({'width': 400, 'height': content_height})
                
                # Take screenshot of just the content (not full page)
                screenshot = page.screenshot(
                    type='png',
                    clip={'x': 0, 'y': 0, 'width': 400, 'height': content_height},
                )
                
                return screenshot
                
            finally:
                browser.close()
    
    def _render_with_wkhtmltoimage(self, html):
        """
        Fallback: Render HTML to PNG using wkhtmltoimage.
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as html_file:
            html_file.write(html)
            html_path = html_file.name
        
        png_path = html_path.replace('.html', '.png')
        
        try:
            cmd = [
                'wkhtmltoimage',
                '--width', '400',
                '--quality', '95',
                '--disable-smart-width',
                '--encoding', 'utf-8',
                html_path,
                png_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            
            if result.returncode != 0:
                _logger.warning("wkhtmltoimage failed: %s", result.stderr.decode('utf-8', errors='ignore'))
                return None
            
            with open(png_path, 'rb') as f:
                return f.read()
                
        finally:
            if os.path.exists(html_path):
                os.unlink(html_path)
            if os.path.exists(png_path):
                os.unlink(png_path)
    
    def _render_label_html(self, pallet):
        """
        Render the pallet label QWeb template to HTML string.
        """
        try:
            import datetime
            
            values = {
                'docs': pallet,
                'pallet': pallet,
                'context_timestamp': lambda dt: dt,
                'datetime': datetime,
                'image_data_uri': self._image_to_data_uri,
            }
            
            html = request.env['ir.qweb']._render(
                'farm_management.report_pallet_label_standalone',
                values,
            )
            
            return html
            
        except Exception as e:
            _logger.exception("Error rendering label HTML: %s", e)
            return None
    
    def _image_to_data_uri(self, image_data):
        """Convert binary image data to data URI for embedding in HTML."""
        if not image_data:
            return ''
        try:
            encoded = base64.b64encode(image_data).decode('utf-8')
            return f'data:image/png;base64,{encoded}'
        except Exception:
            return ''
    
    def _create_pdf_from_images(self, images):
        """
        Create a single-page PDF with all images stitched vertically.
        Adds padding between each label for visual separation.
        Ideal for continuous roll printing.
        """
        try:
            # Padding between images (in pixels)
            PADDING = 40
            
            # Open all images and get dimensions
            pil_images = [Image.open(io.BytesIO(img_bytes)) for img_bytes in images]
            
            # Calculate combined dimensions
            width = max(img.width for img in pil_images)
            total_height = sum(img.height for img in pil_images) + (PADDING * (len(pil_images) - 1))
            
            # Create combined image with white background
            combined = Image.new('RGB', (width, total_height), 'white')
            
            # Paste each image with padding
            y_offset = 0
            for img in pil_images:
                combined.paste(img, (0, y_offset))
                y_offset += img.height + PADDING
            
            # Create single-page PDF
            output = io.BytesIO()
            c = canvas.Canvas(output, pagesize=(width, total_height))
            
            combined_bytes = io.BytesIO()
            combined.save(combined_bytes, format='PNG')
            combined_bytes.seek(0)
            
            c.drawImage(ImageReader(combined_bytes), 0, 0, width, total_height)
            c.save()
            
            return output.getvalue()
            
        except Exception as e:
            _logger.exception("Error creating PDF from images: %s", e)
            return None
    
    def _fallback_to_standard_report(self, pallet_ids):
        """
        Fallback to standard QWeb PDF report if image generation fails.
        """
        try:
            ids = [int(x) for x in pallet_ids.split(',') if x.strip().isdigit()]
            pallets = request.env['sale.order.pallet'].browse(ids)
            report = request.env.ref('farm_management.action_report_pallet_label')
            pdf_content, _ = report._render_qweb_pdf(report.id, pallets.ids)
            
            filename = f"pallet_label.pdf"
            return request.make_response(
                pdf_content,
                headers=[
                    ('Content-Type', 'application/pdf'),
                    ('Content-Disposition', content_disposition(filename)),
                ]
            )
        except Exception as e:
            _logger.exception("Fallback report also failed: %s", e)
            return request.not_found()
