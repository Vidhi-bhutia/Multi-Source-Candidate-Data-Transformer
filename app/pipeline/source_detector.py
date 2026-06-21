"""Source detector component for identifying file types and verifying formats."""

import os
import csv
import logging
import mimetypes

# Set up logging for tracking warnings and errors
logger = logging.getLogger(__name__)

# Check if python-magic is available for robust MIME detection
try:
    import magic
    HAS_MAGIC = True
except ImportError:
    logger.warning("python-magic not installed; falling back to extension-based detection.")
    HAS_MAGIC = False


class SourceDetector:
    """Detects the file type and formats of raw candidate source files."""

    def __init__(self) -> None:
        """Initializes the SourceDetector instance."""
        pass

    def _detect_mime_type(self, file_path: str) -> str:
        """Inspects file headers via python-magic or falls back to extensions."""
        if HAS_MAGIC:
            try:
                # magic.from_file scans headers to verify binary structure
                mime = magic.from_file(file_path, mime=True)
                if mime:
                    return mime
            except Exception as e:
                # Capture missing DLL errors on Windows or other run-time magic faults
                logger.error(f"python-magic failed to detect MIME type: {e}. Falling back to mimetypes.")
        
        # Fallback to file extension guessing if magic is missing or errors out
        mime, _ = mimetypes.guess_type(file_path)
        if mime:
            return mime
            
        # Default binary stream if type cannot be guessed
        return "application/octet-stream"

    def detect(self, file_path: str) -> dict:
        """Determines the source type, check readability, and gathers file metadata."""
        file_name = os.path.basename(file_path)
        extension = os.path.splitext(file_path)[1].lower()

        # Requirement 1: If file does not exist → readable: False, warning: "File not found"
        if not os.path.exists(file_path):
            return {
                "file_path": file_path,
                "file_name": file_name,
                "extension": extension,
                "mime_type": "unknown",
                "detected_type": "unknown",
                "readable": False,
                "file_size_bytes": 0,
                "warning": "File not found"
            }

        # Retrieve file size and catch access errors
        try:
            file_size_bytes = os.path.getsize(file_path)
        except Exception as e:
            logger.error(f"Failed to read file size for {file_path}: {e}")
            return {
                "file_path": file_path,
                "file_name": file_name,
                "extension": extension,
                "mime_type": "unknown",
                "detected_type": "unknown",
                "readable": False,
                "file_size_bytes": 0,
                "warning": f"Unable to read file properties: {str(e)}"
            }

        # Requirement 2: If file size is 0 → readable: False, warning: "Empty file"
        if file_size_bytes == 0:
            return {
                "file_path": file_path,
                "file_name": file_name,
                "extension": extension,
                "mime_type": "unknown",
                "detected_type": "unknown",
                "readable": False,
                "file_size_bytes": 0,
                "warning": "Empty file"
            }

        # Requirement 3: Use python-magic to get MIME type (with robust fallbacks)
        mime_type = self._detect_mime_type(file_path)

        detected_type = "unknown"
        readable = True
        warning = None

        # Requirement 4: Determine detected_type
        # Case A: CSV (MIME is text/csv OR extension is .csv)
        if mime_type == "text/csv" or extension == ".csv":
            detected_type = "csv"
            try:
                # Open with ignore to prevent decoding exceptions on bad binary data
                with open(file_path, mode='r', encoding='utf-8-sig', errors='ignore') as f:
                    reader = csv.reader(f)
                    headers = next(reader, None)
                    if headers:
                        # Normalize headers to find candidate data fields
                        normalized_headers = [h.strip().lower().replace(" ", "_") for h in headers]
                        expected = {"name", "email", "phone", "current_company", "title"}
                        
                        # Requirement 5: Check if CSV contains expected column fields
                        if not any(eh in normalized_headers for eh in expected):
                            warning = "CSV does not contain any expected candidate columns"
                    else:
                        warning = "CSV does not contain any expected candidate columns"
            except Exception as e:
                logger.error(f"Error reading CSV header from {file_path}: {e}")
                readable = False
                warning = f"Unreadable CSV format: {str(e)}"

        # Case B: PDF (MIME is application/pdf)
        elif mime_type == "application/pdf":
            try:
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    text = ""
                    # Scanned check: read from the first 3 pages
                    for page in pdf.pages[:3]:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text
                    
                    # Scanned PDF logic: text length < 100 characters
                    if len(text) < 100:
                        detected_type = "image_pdf"
                        warning = "PDF appears to be scanned/image-based. Text extraction will be attempted with OCR."
                    else:
                        detected_type = "pdf"
            except Exception as e:
                logger.error(f"Error reading PDF from {file_path}: {e}")
                readable = False
                detected_type = "unknown"
                warning = f"Corrupted or unreadable PDF: {str(e)}"

        # Case C: DOCX (MIME is Word document OR extension is .docx)
        elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or extension == ".docx":
            detected_type = "docx"
            try:
                import docx
                # Attempt to open document to verify file integrity
                docx.Document(file_path)
            except Exception as e:
                logger.error(f"Error reading DOCX from {file_path}: {e}")
                readable = False
                detected_type = "unknown"
                warning = f"Corrupted or unreadable DOCX: {str(e)}"

        # Case D: Raw Image (MIME starts with image/)
        elif mime_type.startswith("image/"):
            detected_type = "unknown"
            warning = "Raw image files not supported. Convert to PDF first."

        # Case E: Anything else
        else:
            detected_type = "unknown"
            warning = f"Unsupported file type: {mime_type}"

        return {
            "file_path": file_path,
            "file_name": file_name,
            "extension": extension,
            "mime_type": mime_type,
            "detected_type": detected_type,
            "readable": readable,
            "file_size_bytes": file_size_bytes,
            "warning": warning
        }
