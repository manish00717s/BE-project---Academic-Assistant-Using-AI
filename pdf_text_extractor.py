"""
PDF Text Extraction Utility
Supports multiple extraction methods for robust text extraction from PDFs
"""

import os
import PyPDF2
import pytesseract
from pdf2image import convert_from_path
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError
try:
    import fitz  # PyMuPDF (optional fallback if poppler is not available)
except Exception:
    fitz = None
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except Exception:
    CV2_AVAILABLE = False
from PIL import Image, ImageFilter, ImageEnhance
import re
import argparse
import sys


class PDFTextExtractor:
    """
    Comprehensive PDF text extraction with multiple fallback methods
    """

    def __init__(self):
        """Initialize the PDF extractor"""
        # Configure pytesseract path if needed (Windows)
        # Allow overriding tesseract executable via environment variable
        # Set `TESSERACT_CMD` to the full path of tesseract executable if needed
        try:
            env_cmd = os.environ.get('TESSERACT_CMD')
            if env_cmd and os.path.exists(env_cmd):
                pytesseract.pytesseract.tesseract_cmd = env_cmd
            else:
                # If on Windows and tesseract is installed in the common location, use it
                default_win = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                if os.name == 'nt' and os.path.exists(default_win):
                    pytesseract.pytesseract.tesseract_cmd = default_win
        except Exception:
            # If something goes wrong setting the path, continue — errors will surface during OCR
            pass

    def extract_text_from_pdf(self, pdf_path):
        """
        Main method to extract text from PDF
        Tries multiple methods for best results

        Args:
            pdf_path: Path to the PDF file

        Returns:
            str: Extracted text from PDF
        """

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        # Try Method 1: PyPDF2 (fast, works for text-based PDFs)
        try:
            text = self._extract_with_pypdf2(pdf_path)
            if text and len(text.strip()) > 100:  # If we got substantial text
                print(f"✓ Successfully extracted text using PyPDF2 ({len(text)} characters)")
                return self._clean_text(text)
        except Exception as e:
            print(f"PyPDF2 extraction failed: {str(e)}")

        # Try Method 2: OCR (slower, works for scanned PDFs)
        try:
            text = self._extract_with_ocr(pdf_path)
            if text and len(text.strip()) > 50:
                print(f"✓ Successfully extracted text using OCR ({len(text)} characters)")
                return self._clean_text(text)
        except Exception as e:
            print(f"OCR extraction failed: {str(e)}")

        # If both methods fail, return error message
        return "Failed to extract text from PDF. Please ensure the PDF is readable."

    def _extract_with_pypdf2(self, pdf_path):
        """
        Extract text using PyPDF2 library
        Works best for digital/text-based PDFs
        """
        text = ""

        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            num_pages = len(pdf_reader.pages)

            print(f"Processing {num_pages} pages with PyPDF2...")

            for page_num in range(num_pages):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()

                if page_text:
                    text += f"\n--- Page {page_num + 1} ---\n"
                    text += page_text

        return text

    def _preprocess_image(self, image):
        """
        Preprocess image for better OCR accuracy.
        Applies grayscale conversion, denoising, and Otsu thresholding.

        Args:
            image: PIL Image

        Returns:
            PIL Image: preprocessed image
        """
        if CV2_AVAILABLE:
            # Convert PIL to numpy array (RGB)
            img = np.array(image.convert("RGB"))

            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

            # Denoise
            denoised = cv2.fastNlMeansDenoising(gray, h=10)

            # Apply Otsu thresholding to get clean black/white image
            _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            return Image.fromarray(thresh)
        else:
            # Fallback: PIL-only preprocessing
            image = image.convert("L")  # Grayscale
            image = image.filter(ImageFilter.SHARPEN)
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.0)
            return image

    def _extract_with_ocr(self, pdf_path):
        """
        Extract text using OCR (Optical Character Recognition)
        Works for scanned PDFs and images
        Requires: pytesseract and pdf2image (or PyMuPDF as fallback)
        """
        text = ""

        # Convert PDF to images
        print("Converting PDF to images for OCR...")
        images = []

        try:
            images = convert_from_path(pdf_path)

        except (PDFInfoNotInstalledError, PDFPageCountError) as e:
            # Common pdf2image error when poppler is missing on PATH (Windows)
            msg = str(e)
            print(f"pdf2image error: {msg}")

            # Fallback: try to use PyMuPDF (fitz) if available
            if fitz is not None:
                print("Poppler not found — falling back to PyMuPDF for rendering pages.")
                doc = fitz.open(pdf_path)

                for page in doc:
                    # Render at 4x scale for higher resolution (better OCR accuracy)
                    mat = fitz.Matrix(4, 4)
                    pix = page.get_pixmap(matrix=mat)
                    mode = "RGBA" if pix.alpha else "RGB"
                    try:
                        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                    except Exception:
                        # Fallback to saving to PNG bytes and reloading via PIL
                        from io import BytesIO
                        img_bytes = pix.tobytes(output="png")
                        img = Image.open(BytesIO(img_bytes)).convert("RGB")

                    images.append(img)

            else:
                # Neither poppler nor PyMuPDF available — provide actionable error
                raise RuntimeError(
                    "Unable to convert PDF to images: poppler not found and PyMuPDF (fitz) not installed. "
                    "On Windows, install poppler (https://blog.alivate.com.au/poppler-windows/) and add its 'bin' directory to PATH, "
                    "or install PyMuPDF via 'pip install pymupdf' to enable a fallback renderer.")

        except Exception as e:
            # Other unexpected errors from pdf2image
            print(f"Unexpected error converting PDF: {str(e)}")
            raise

        print(f"Processing {len(images)} pages with OCR...")

        for i, image in enumerate(images):
            # Ensure image is PIL Image
            if not isinstance(image, Image.Image):
                image = Image.fromarray(image)

            # Preprocess image for better OCR accuracy
            image = self._preprocess_image(image)

            # Perform OCR on each page with optimized config
            # --psm 6: Assume a single uniform block of text
            # --oem 3: Use LSTM + Legacy engine (best accuracy)
            try:
                page_text = pytesseract.image_to_string(
                    image,
                    config='--psm 6 --oem 3'
                )
            except Exception as e:
                # Common case: tesseract not installed or not in PATH
                err_msg = str(e)
                tesseract_missing = False
                try:
                    from pytesseract.pytesseract import TesseractNotFoundError
                    if isinstance(e, TesseractNotFoundError):
                        tesseract_missing = True
                except Exception:
                    if 'tesseract' in err_msg.lower() and ('not found' in err_msg.lower() or 'is not installed' in err_msg.lower()):
                        tesseract_missing = True

                if tesseract_missing:
                    raise RuntimeError(
                        "tesseract is not installed or it's not in your PATH. "
                        "Install Tesseract OCR (https://github.com/tesseract-ocr/tesseract) and ensure the executable is in PATH, "
                        "or set the full path via environment variable TESSERACT_CMD.")
                else:
                    raise

            if page_text:
                text += f"\n--- Page {i + 1} ---\n"
                text += page_text

        return text

    def _clean_text(self, text):
        """
        Clean and format extracted text
        Remove extra spaces, fix line breaks, etc.
        """
        if not text:
            return ""

        # Remove multiple spaces
        text = re.sub(r' +', ' ', text)

        # Remove multiple newlines
        text = re.sub(r'\n\s*\n', '\n\n', text)

        # Strip leading/trailing whitespace
        text = text.strip()

        # Remove null bytes
        text = text.replace('\x00', '')

        return text

    def extract_text_by_page(self, pdf_path):
        """
        Extract text page by page (useful for large PDFs)

        Returns:
            list: List of strings, one per page
        """
        pages = []

        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)

                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text()
                    pages.append(self._clean_text(page_text))

        except Exception as e:
            print(f"Error extracting text by page: {str(e)}")

        return pages

    def get_pdf_info(self, pdf_path):
        """
        Get metadata information about the PDF

        Returns:
            dict: PDF metadata
        """
        info = {
            'num_pages': 0,
            'file_size': 0,
            'has_text': False
        }

        try:
            # Get file size
            info['file_size'] = os.path.getsize(pdf_path)

            # Get number of pages
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                info['num_pages'] = len(pdf_reader.pages)

                # Check if PDF has extractable text
                if info['num_pages'] > 0:
                    first_page_text = pdf_reader.pages[0].extract_text()
                    info['has_text'] = bool(first_page_text and len(first_page_text.strip()) > 10)

        except Exception as e:
            print(f"Error getting PDF info: {str(e)}")

        return info


# Create global instance
pdf_extractor = PDFTextExtractor()


def extract_text_from_pdf(pdf_path):
    """
    Convenience function for easy import

    Args:
        pdf_path: Path to PDF file

    Returns:
        str: Extracted text
    """
    return pdf_extractor.extract_text_from_pdf(pdf_path)


# Example usage and testing
if __name__ == '__main__':
    default_test = r'C:/Users/shiva/Downloads/DL ass 4.pdf'

    parser = argparse.ArgumentParser(description='Extract text from a PDF using multiple strategies.')
    parser.add_argument('pdf', nargs='?', default=default_test, help='Path to the PDF file (default: test.pdf)')
    parser.add_argument('-o', '--out', help='Write extracted text to a file instead of printing')
    args = parser.parse_args()

    pdf_path = args.pdf

    if not os.path.exists(pdf_path):
        print(f"PDF not found: {pdf_path}")
        sys.exit(1)

    print(f"Processing: {pdf_path}")
    info = pdf_extractor.get_pdf_info(pdf_path)
    print(f"\nPDF Info:")
    print(f"  Pages: {info['num_pages']}")
    print(f"  Size: {info['file_size']} bytes")
    print(f"  Has extractable text: {info['has_text']}")

    text = extract_text_from_pdf(pdf_path)
    output = text if text else ''

    if args.out:
        try:
            with open(args.out, 'w', encoding='utf-8') as fh:
                fh.write(output)
            print(f"\nExtracted text written to: {args.out}")
        except Exception as e:
            print(f"Failed to write output file: {e}")
            print(f"\nExtracted text ({len(output)} characters):")
            print(output)
    else:
        print(f"\nExtracted text ({len(output)} characters):")
        print(output)


# Initialize generator
pdf_to_text = PDFTextExtractor()