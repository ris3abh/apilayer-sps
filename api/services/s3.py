# api/services/s3.py
import boto3
from typing import Optional
from datetime import timedelta
from botocore.exceptions import ClientError
from api.config import settings
from api.models.document import DocumentType

class S3Service:
    def __init__(self):
        self.s3_client = boto3.client('s3', region_name=settings.AWS_REGION)
        self.documents_bucket = settings.DOCUMENTS_BUCKET
        self.outputs_bucket = settings.OUTPUTS_BUCKET
    
    def _get_document_prefix(self, client_id: str, document_type: DocumentType) -> str:
        """Generate S3 key prefix based on document type"""
        type_mapping = {
            DocumentType.BRAND_VOICE: "brand-voice",
            DocumentType.STYLE_GUIDE: "style-guides",
            DocumentType.SAMPLE_CONTENT: "sample-content",
            DocumentType.MARKETING_MATERIAL: "marketing-materials",
            DocumentType.PREVIOUS_WORK: "previous-work"
        }
        folder = type_mapping.get(document_type, "other")
        return f"{client_id}/{folder}"
    
    def generate_upload_presigned_url(
        self, 
        client_id: str,
        document_type: DocumentType,
        file_name: str,
        mime_type: str,
        expires_in: int = 3600
    ) -> tuple[str, str]:
        """
        Generate presigned URL for uploading a document
        Returns: (presigned_url, s3_key)
        """
        prefix = self._get_document_prefix(client_id, document_type)
        s3_key = f"{prefix}/{file_name}"
        
        try:
            presigned_url = self.s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': self.documents_bucket,
                    'Key': s3_key,
                    'ContentType': mime_type
                },
                ExpiresIn=expires_in
            )
            return presigned_url, s3_key
        except ClientError as e:
            raise ValueError(f"Failed to generate upload URL: {str(e)}")
    
    def generate_download_presigned_url(
        self,
        s3_key: str,
        bucket: Optional[str] = None,
        expires_in: int = 3600
    ) -> str:
        """Generate presigned URL for downloading a document"""
        bucket = bucket or self.documents_bucket
        
        try:
            presigned_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket,
                    'Key': s3_key
                },
                ExpiresIn=expires_in
            )
            return presigned_url
        except ClientError as e:
            raise ValueError(f"Failed to generate download URL: {str(e)}")
    
    def delete_document(self, s3_key: str, bucket: Optional[str] = None) -> bool:
        """Delete a document from S3"""
        bucket = bucket or self.documents_bucket
        
        try:
            self.s3_client.delete_object(
                Bucket=bucket,
                Key=s3_key
            )
            return True
        except ClientError as e:
            raise ValueError(f"Failed to delete document: {str(e)}")
    
    def list_documents(self, client_id: str, document_type: Optional[DocumentType] = None) -> list:
        """List documents for a client"""
        if document_type:
            prefix = self._get_document_prefix(client_id, document_type)
        else:
            prefix = f"{client_id}/"
        
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.documents_bucket,
                Prefix=prefix
            )
            
            documents = []
            for obj in response.get('Contents', []):
                documents.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified']
                })
            
            return documents
        except ClientError as e:
            raise ValueError(f"Failed to list documents: {str(e)}")
    
    def upload_content_output(self, execution_id: str, content: str, file_name: str) -> str:
        """Upload generated content to outputs bucket"""
        s3_key = f"{execution_id}/{file_name}"
        
        try:
            self.s3_client.put_object(
                Bucket=self.outputs_bucket,
                Key=s3_key,
                Body=content.encode('utf-8'),
                ContentType='text/markdown'
            )
            return s3_key
        except ClientError as e:
            raise ValueError(f"Failed to upload content: {str(e)}")

# Singleton instance
s3_service = S3Service()