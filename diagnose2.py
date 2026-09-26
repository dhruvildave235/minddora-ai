from app import create_app
from app.models.document import Document
from app.models.chunk import Chunk

app = create_app()

with app.app_context():
    docs = Document.query.order_by(Document.id.desc()).all()
    latest = docs[0]
    print(f"Latest document: id={latest.id} title={latest.title!r} status={latest.processing_status} total_chunks={latest.total_chunks}")
    print("=" * 70)

    chunks = Chunk.query.filter_by(document_id=latest.id).order_by(Chunk.chunk_index).all()
    for c in chunks:
        print(f"\n--- Chunk {c.chunk_index} (id={c.id}) ---")
        print(c.chunk_text)
        print(f"[contains 'cgpa': {'cgpa' in c.chunk_text.lower()}]")