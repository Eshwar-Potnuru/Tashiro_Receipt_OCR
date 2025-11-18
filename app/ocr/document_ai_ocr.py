"""
Google Document AI OCR Engine for Receipt Processing
Provides structured document understanding for receipts and invoices
"""

import base64
import logging
from typing import Dict, Optional, List, Any, Tuple
from google.cloud import documentai_v1
from google.cloud.documentai_v1 import types
from google.oauth2 import service_account
import json
import os

logger = logging.getLogger(__name__)

class DocumentAIOCR:
    """Google Document AI OCR engine for structured receipt processing"""
    
    def __init__(self):
        """Initialize Document AI client"""
        self.client: Optional[documentai_v1.DocumentProcessorServiceClient] = None
        self.processor_name: Optional[str] = None
        self.project_id: Optional[str] = None
        self.location = os.getenv('DOCUMENT_AI_LOCATION', 'us')
        self.processor_id = os.getenv('DOCUMENT_AI_PROCESSOR_ID')

        credentials, project_id = self._load_credentials()
        self.project_id = project_id

        if not credentials:
            logger.warning(
                "Document AI credentials not configured. Set DOCUMENT_AI_CREDENTIALS_PATH or GOOGLE_APPLICATION_CREDENTIALS, "
                "or provide DOCUMENT_AI_CREDENTIALS_JSON/B64."
            )
            return

        try:
            client_options = {"api_endpoint": f"{self.location}-documentai.googleapis.com"}
            self.client = documentai_v1.DocumentProcessorServiceClient(
                credentials=credentials,
                client_options=client_options
            )
            logger.info("Document AI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Document AI: {str(e)}")
            self.client = None
            return

        processor_name_env = os.getenv('DOCUMENT_AI_PROCESSOR_NAME')
        if processor_name_env:
            self.processor_name = processor_name_env
        elif self.processor_id and self.project_id:
            self.processor_name = (
                f"projects/{self.project_id}/locations/{self.location}/processors/{self.processor_id}"
            )
        else:
            logger.warning(
                "Document AI processor not configured. Set DOCUMENT_AI_PROCESSOR_ID (and ensure credentials include project_id) "
                "or DOCUMENT_AI_PROCESSOR_NAME."
            )

    def _load_credentials(self) -> Tuple[Optional['service_account.Credentials'], Optional[str]]:
        """Load Document AI credentials from file or environment."""
        credential_scopes = ['https://www.googleapis.com/auth/cloud-platform']

        candidate_path = os.getenv('DOCUMENT_AI_CREDENTIALS_PATH') or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if candidate_path:
            if os.path.exists(candidate_path):
                try:
                    creds = service_account.Credentials.from_service_account_file(
                        candidate_path,
                        scopes=credential_scopes
                    )
                    return creds, creds.project_id
                except Exception as exc:
                    logger.warning(f"Failed to load Document AI credentials from {candidate_path}: {exc}")
            else:
                logger.warning(f"Document AI credential file not found: {candidate_path}")

        inline_payload = (
            os.getenv('DOCUMENT_AI_CREDENTIALS_JSON')
            or os.getenv('GOOGLE_VISION_CREDENTIALS_JSON')
            or os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
            or os.getenv('GOOGLE_APPLICATION_CREDENTIALS_CONTENT')
        )
        inline_payload = inline_payload.strip() if inline_payload else None
        if not inline_payload:
            inline_b64 = (
                os.getenv('DOCUMENT_AI_CREDENTIALS_B64')
                or os.getenv('GOOGLE_VISION_CREDENTIALS_B64')
            )
            if inline_b64:
                try:
                    inline_payload = base64.b64decode(inline_b64).decode('utf-8').strip()
                except Exception as exc:
                    logger.warning(f"Failed to decode DOCUMENT_AI_CREDENTIALS_B64: {exc}")

        if inline_payload:
            try:
                creds_info = json.loads(inline_payload)
                creds = service_account.Credentials.from_service_account_info(
                    creds_info,
                    scopes=credential_scopes
                )
                project_id = creds_info.get('project_id') or creds.project_id
                return creds, project_id
            except Exception as exc:
                logger.warning(f"Invalid Document AI credentials JSON: {exc}")

        return None, None
    
    def is_available(self) -> bool:
        """Check if Document AI is available"""
        return self.client is not None and self.processor_name is not None
    
    def extract_structured_data(self, image_data: bytes) -> Dict[str, Any]:
        """
        Extract structured data from receipt using Document AI
        
        Args:
            image_data: Image bytes
            
        Returns:
            Dict with structured receipt data
        """
        if not self.is_available():
            logger.warning("Document AI not available")
            return {}
        
        try:
            # Create the document object
            document = types.Document(
                content=image_data,
                mime_type="image/png"  # Adjust based on your image type
            )
            
            # Create the request
            request = types.ProcessRequest(
                name=self.processor_name,
                document=document
            )
            
            # Process the document
            logger.info("Processing document with Document AI...")
            result = self.client.process_document(request=request)
            document = result.document
            
            # Extract structured data
            structured_data = self._parse_document_ai_response(document)
            
            logger.info(f"Document AI extracted {len(structured_data)} fields")
            return structured_data
            
        except Exception as e:
            logger.error(f"Document AI extraction failed: {str(e)}")
            return {}
    
    def _parse_document_ai_response(self, document) -> Dict[str, Any]:
        """
        Parse Document AI response into structured receipt data
        
        Args:
            document: Document AI response document
            
        Returns:
            Dict with extracted receipt fields
        """
        result = {
            'raw_text': document.text,
            'entities': {},
            'line_items': [],
            'totals': {},
            'confidence_scores': {}
        }
        
        # Extract entities (structured fields)
        for entity in document.entities:
            entity_type = entity.type_
            entity_text = self._get_entity_text(document, entity)
            confidence = entity.confidence
            
            result['entities'][entity_type] = {
                'text': entity_text,
                'confidence': confidence
            }
            result['confidence_scores'][entity_type] = confidence
            
            # Map common receipt fields
            if entity_type in ['total_amount', 'net_amount', 'total']:
                result['totals']['total'] = entity_text
            elif entity_type in ['supplier_name', 'vendor_name', 'merchant_name']:
                result['entities']['vendor'] = entity_text
            elif entity_type in ['invoice_date', 'receipt_date', 'date']:
                result['entities']['date'] = entity_text
            elif entity_type in ['invoice_id', 'receipt_id', 'document_id']:
                result['entities']['invoice_number'] = entity_text
        
        # Extract line items
        if hasattr(document, 'pages') and document.pages:
            for page in document.pages:
                if hasattr(page, 'tables') and page.tables:
                    for table in page.tables:
                        line_items = self._extract_line_items_from_table(document, table)
                        result['line_items'].extend(line_items)
        
        logger.info(f"Parsed entities: {list(result['entities'].keys())}")
        logger.info(f"Found {len(result['line_items'])} line items")
        
        return result
    
    def _get_entity_text(self, document, entity) -> str:
        """Extract text from Document AI entity"""
        try:
            if hasattr(entity, 'mention_text'):
                return entity.mention_text
            elif hasattr(entity, 'text_anchor') and entity.text_anchor.text_segments:
                text_segment = entity.text_anchor.text_segments[0]
                start = int(text_segment.start_index) if text_segment.start_index else 0
                end = int(text_segment.end_index) if text_segment.end_index else len(document.text)
                return document.text[start:end]
            else:
                return str(entity)
        except Exception as e:
            logger.error(f"Failed to extract entity text: {str(e)}")
            return ""
    
    def _extract_line_items_from_table(self, document, table) -> List[Dict[str, str]]:
        """Extract line items from Document AI table"""
        line_items = []
        
        try:
            headers = []
            
            # Extract headers
            if table.header_rows:
                header_row = table.header_rows[0]
                for cell in header_row.cells:
                    header_text = self._get_cell_text(document, cell)
                    headers.append(header_text)
            
            # Extract data rows
            for row in table.body_rows:
                item = {}
                for i, cell in enumerate(row.cells):
                    cell_text = self._get_cell_text(document, cell)
                    header = headers[i] if i < len(headers) else f"column_{i}"
                    item[header] = cell_text
                
                if item:  # Only add non-empty items
                    line_items.append(item)
        
        except Exception as e:
            logger.error(f"Failed to extract line items: {str(e)}")
        
        return line_items
    
    def _get_cell_text(self, document, cell) -> str:
        """Extract text from Document AI table cell"""
        try:
            if hasattr(cell, 'layout') and cell.layout.text_anchor:
                text_segments = cell.layout.text_anchor.text_segments
                if text_segments:
                    segment = text_segments[0]
                    start = int(segment.start_index) if segment.start_index else 0
                    end = int(segment.end_index) if segment.end_index else len(document.text)
                    return document.text[start:end].strip()
            return ""
        except Exception as e:
            logger.error(f"Failed to extract cell text: {str(e)}")
            return ""
    
    def extract_text_fallback(self, image_data: bytes) -> str:
        """
        Fallback text extraction using Document AI
        
        Args:
            image_data: Image bytes
            
        Returns:
            Extracted text string
        """
        structured_data = self.extract_structured_data(image_data)
        return structured_data.get('raw_text', '')