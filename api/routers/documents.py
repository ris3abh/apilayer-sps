# api/routers/documents.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID

from api.database import get_db
from api.models.document import Document, DocumentType
from api.models.user import User
from api.models.client import Client
from api.schemas.document import (
    DocumentUploadRequest,
    DocumentUploadResponse,
    DocumentResponse,
    DocumentDownloadResponse,
    DocumentListResponse
)
from api.services.s3 import s3_service
from api.routers.auth import get_current_user

router = APIRouter()

@router.post("/client/{client_id}/upload-url", response_model=DocumentUploadResponse)
async def generate_upload_url(
    client_id: UUID,
    request: DocumentUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate a presigned URL for uploading a document to S3.
    Documents are organized in S3 as: client_id/{document_type}/filename
    
    Document types map to folders:
    - BRAND_VOICE -> brand-voice/
    - STYLE_GUIDE -> style-guides/
    - SAMPLE_CONTENT -> sample-content/
    - MARKETING_MATERIAL -> marketing-materials/
    - PREVIOUS_WORK -> previous-work/
    """
    # Verify client exists
    client = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    try:
        # Generate presigned URL - S3 service handles folder structure
        presigned_url, s3_key = s3_service.generate_upload_presigned_url(
            client_id=str(client_id),
            document_type=request.document_type,
            file_name=request.file_name,
            mime_type=request.mime_type,
            expires_in=3600
        )
        
        # Create document record in database
        document = Document(
            client_id=client_id,
            document_type=request.document_type,
            file_name=request.file_name,
            s3_bucket=s3_service.documents_bucket,
            s3_key=s3_key,
            file_size=request.file_size,
            mime_type=request.mime_type,
            uploaded_by=current_user.user_id,
            version=1
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
        return DocumentUploadResponse(
            document_id=document.document_id,
            presigned_url=presigned_url,
            s3_key=s3_key,
            expires_in=3600
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate upload URL: {str(e)}"
        )

@router.get("/{document_id}/download-url", response_model=DocumentDownloadResponse)
async def generate_download_url(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate a presigned URL for downloading a document from S3
    """
    document = db.query(Document).filter(Document.document_id == document_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    try:
        download_url = s3_service.generate_download_presigned_url(
            s3_key=document.s3_key,
            bucket=document.s3_bucket,
            expires_in=3600
        )
        
        return DocumentDownloadResponse(
            document_id=document.document_id,
            file_name=document.file_name,
            presigned_url=download_url,
            expires_in=3600
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate download URL: {str(e)}"
        )

@router.get("/client/{client_id}", response_model=DocumentListResponse)
async def list_client_documents(
    client_id: UUID,
    document_type: Optional[DocumentType] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all documents for a client, optionally filtered by document type.
    
    This shows all documents across all 5 folders:
    - brand-voice/
    - style-guides/
    - sample-content/
    - marketing-materials/
    - previous-work/
    """
    query = db.query(Document).filter(Document.client_id == client_id)
    
    if document_type:
        query = query.filter(Document.document_type == document_type)
    
    documents = query.order_by(Document.uploaded_at.desc()).all()
    
    return DocumentListResponse(
        documents=[DocumentResponse.from_orm(doc) for doc in documents],
        total=len(documents)
    )

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get document metadata by ID"""
    document = db.query(Document).filter(Document.document_id == document_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    return DocumentResponse.from_orm(document)

@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a document from both S3 and database"""
    document = db.query(Document).filter(Document.document_id == document_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    try:
        # Delete from S3
        s3_service.delete_document(
            s3_key=document.s3_key,
            bucket=document.s3_bucket
        )
        
        # Delete from database
        db.delete(document)
        db.commit()
        
        return {
            "message": "Document deleted successfully",
            "document_id": document_id
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )
