"""
Celery tasks for asynchronous product AI processing.
Handles image vision processing, document generation, and embeddings.
"""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def generate_ai_document_for_product(self, product_id: str):
    """
    Complete async pipeline for product AI document generation and embedding.
    
    Flow:
    1. Get product and images
    2. Process images with vision model -> vision_text  (graceful on failure)
    3. Get product base text -> product_text
    4. Combine both texts
    5. Create/update AIDocument
    6. Generate embedding vector  (graceful on failure -> zero vector)
    7. Store embedding in AIDocumentEmbedding
    
    Args:
        product_id: UUID of product to process
        
    Returns:
        Dict with status and embedding_id
    """
    from .models import Product, AIDocument, AIDocumentEmbedding
    from .services import ProductService
    from .ai_service import AIService
    
    try:
        # 1. Get product
        product = Product.objects.select_related('category').prefetch_related(
            'attributes', 'images'
        ).get(id=product_id)
        logger.info(f"[AI Task] Processing product: {product.title}")
        
        # 2. Initialize AI service
        ai_service = AIService()
        
        # 3. Process images with vision model (graceful – never crashes)
        product_images = list(product.images.all())
        vision_text = "No images available for analysis."
        
        if product_images:
            try:
                vision_text = ai_service.process_product_images(product_images)
                logger.info(f"[AI Task] Vision text generated for {product.title}")
            except Exception as e:
                logger.warning(f"[AI Task] Vision processing failed for {product.title}: {e}")
                vision_text = f"Vision analysis unavailable: {str(e)[:100]}"
        else:
            logger.info(f"[AI Task] No images found for product {product.title}")
        
        # 4. Get product base text (always works – no external deps)
        product_text = ProductService.generate_product_text(product)
        logger.info(f"[AI Task] Product text generated for {product.title}")
        
        # 5. Combine texts
        combined_text = f"""VISION ANALYSIS:
{vision_text}

PRODUCT INFORMATION:
{product_text}"""
        
        # 6. Create/update AIDocument
        ai_document, created = AIDocument.objects.update_or_create(
            source_type='product',
            source_id=str(product.id),
            defaults={
                'text_content': combined_text,
                'metadata_json': {
                    'product_title': product.title,
                    'category': product.category.name,
                    'price': float(product.price),
                    'currency': product.currency,
                    'rating': product.rating_avg,
                    'rating_count': product.rating_count,
                    'in_stock': product.stock_quantity > 0,
                    'image_count': len(product_images),
                    'has_vision_analysis': bool(product_images),
                }
            }
        )
        
        doc_status = 'created' if created else 'updated'
        logger.info(f"[AI Task] AIDocument {doc_status} for {product.title}")
        
        # 7. Generate embedding vector (graceful – returns zeros on failure)
        embedding_vector = ai_service.generate_embedding(combined_text)
        is_real_embedding = any(v != 0.0 for v in embedding_vector[:10])
        metadata = ai_service.get_embedding_metadata(product)
        metadata['is_real_embedding'] = is_real_embedding
        
        # 8. Store embedding
        embedding_obj, emb_created = AIDocumentEmbedding.objects.update_or_create(
            document=ai_document,
            defaults={
                'embedding': embedding_vector,
                'metadata_json': metadata,
            }
        )
        
        # Mark document as indexed
        ai_document.is_indexed = True
        ai_document.save(update_fields=['is_indexed'])
        
        emb_status = 'created' if emb_created else 'updated'
        logger.info(f"[AI Task] AIDocumentEmbedding {emb_status} for {product.title}")
        
        return {
            'status': 'success',
            'product_id': str(product_id),
            'product_title': product.title,
            'document_id': str(ai_document.id),
            'embedding_id': str(embedding_obj.id),
            'document_status': doc_status,
            'embedding_status': emb_status,
            'is_real_embedding': is_real_embedding,
            'message': f"AI document and embedding processed for {product.title}",
        }
    
    except Product.DoesNotExist:
        logger.error(f"[AI Task] Product not found: {product_id}")
        return {
            'status': 'error',
            'product_id': str(product_id),
            'message': f"Product with ID {product_id} not found",
        }
    
    except Exception as exc:
        logger.error(f"[AI Task] Error processing product {product_id}: {exc}")
        # Retry with exponential backoff: 60s, 120s, 240s
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error(f"[AI Task] Max retries exceeded for product {product_id}")
            return {
                'status': 'failed',
                'product_id': str(product_id),
                'message': f"Failed after {self.max_retries} retries: {str(exc)[:200]}",
            }


@shared_task(bind=True, max_retries=0)
def batch_generate_ai_documents(self, product_ids: list):
    """
    Process multiple products in batch.
    
    Runs each product sequentially inside a single task
    (avoids complex group tracking issues).
    
    Args:
        product_ids: List of product UUIDs to process
        
    Returns:
        Summary dict with per-product results
    """
    results = []
    succeeded = 0
    failed = 0
    
    for pid in product_ids:
        try:
            result = generate_ai_document_for_product.apply(args=[str(pid)])
            task_result = result.result if result else {'status': 'unknown'}
            results.append(task_result)
            if task_result.get('status') == 'success':
                succeeded += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"[Batch] Failed processing product {pid}: {e}")
            results.append({
                'status': 'error',
                'product_id': str(pid),
                'message': str(e)[:200],
            })
            failed += 1
    
    logger.info(f"[Batch] Completed: {succeeded} succeeded, {failed} failed out of {len(product_ids)}")
    
    return {
        'status': 'completed',
        'total': len(product_ids),
        'succeeded': succeeded,
        'failed': failed,
        'results': results,
    }
