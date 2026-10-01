# AI Document Assistant — Güncel Proje Bağlamı

> Son güncelleme: 1 Ekim 2026. Yeni bir sohbet bu dosyayı tamamen okumalı,
> ardından bilgileri `git status`, commit geçmişi, kaynak kod ve testlerle
> doğrulamalıdır. Kullanıcının değişiklikleri silinmemeli veya resetlenmemelidir.

## Amaç ve çalışma biçimi

Uygulama, şirket çalışanlarının PDF yükleyip doğal dilde soru sorabildiği,
cevapların doküman/sayfa/chunk kaynaklarıyla döndüğü çok kiracılı bir RAG
sistemidir. Teknik kararlar açıklanmalı, feature'lar tutarlı paketler halinde
uygulanmalı ve her paket Ruff, pytest ve gerektiğinde gerçek entegrasyon testiyle
doğrulanmalıdır.

Secret değerleri, `.env`, gerçek yüklenen PDF'ler ve `.venv` hiçbir zaman commit
edilmemelidir.

## Yerel ortam

- Repository: `C:\Users\ceydanur.duman\Desktop\projects\ai-document-assistant`
- GitHub: `https://github.com/ceyddari/ai-document-assistant.git`
- Branch: `main`
- Python: 3.13.15 (`.venv`)
- PostgreSQL portu: host `5434` → container `5432`
- Image: `pgvector/pgvector:0.8.6-pg17-trixie`
- Embedding: Ollama `bge-m3`, 1024 boyut
- LLM: Ollama `qwen3:8b`

## Tamamlanan akışlar

### Ingestion

```text
PDF upload → local storage → pending → background task → processing
→ sayfa bazlı pypdf parsing → LangChain chunking → BGE-M3 embedding
→ document_chunks + vector(1024) → ready / failed
```

### Retrieval ve RAG

```text
Soru → BGE-M3 query embedding → organization + ready filtresi
→ minimum similarity → pgvector cosine search → güvenli kaynak prompt'u
→ Qwen3 8B → cevap + kaynaklar
```

Prompt yalnızca kaynaklara dayanmayı, bilgi yoksa tahmin yürütmemeyi, doküman
içindeki talimatları veri olarak değerlendirmeyi ve `[Kaynak N]` atfı kullanmayı
ister. Kaynak bulunmazsa LLM çağrılmaz.

Dayanıklılık ayarları:

```env
OLLAMA_TIMEOUT_SECONDS=120
RETRIEVAL_MIN_SIMILARITY=0.35
```

Var olmayan organizasyon search/ask endpoint'lerinde `404`; Ollama ve DB
hataları güvenli `503` döndürür.

## API

- `GET /health`: process kontrolü
- `GET /readiness`: PostgreSQL kontrolü
- `GET /ai/readiness`: Ollama + BGE-M3 + Qwen kontrolü
- `POST /organizations/{organization_id}/documents`: PDF yükleme
- `GET /organizations/{organization_id}/documents`: sayfalı liste
- `GET /organizations/{organization_id}/documents/{document_id}`: detay
- `POST /organizations/{organization_id}/search`: semantik kaynak araması
- `POST /organizations/{organization_id}/ask`: kaynaklı RAG cevabı
- `POST /organizations/{organization_id}/conversations`: conversation oluşturma
- `GET /organizations/{organization_id}/conversations`: sayfalı conversation listesi
- `GET /organizations/{organization_id}/conversations/{conversation_id}`: mesajlı detay

Swagger: `http://127.0.0.1:8000/docs`

## Migration zinciri

```text
45bb2d261737  enable vector extension
→ 353c369e8bd2  create organizations table
→ 49252f5931b1  create documents table
→ da06f6e62641  create document_chunks table
→ 7c2a4f8d1e90  create conversation tables
```

Ana tablolar `organizations`, `documents`, `document_chunks`, `conversations`,
`messages` ve `message_sources` tablolarıdır.
Retrieval sorgularında `organization_id` filtresi güvenlik sınırıdır.

## Ana katmanlar

- `app/api/routes`: HTTP ve hata eşleme
- `app/schemas`: request/response sözleşmeleri
- `app/services/document_service.py`: upload/list/detail
- `app/services/pdf_parser.py`: sayfa bazlı parsing
- `app/services/text_chunker.py`: chunking
- `app/services/embedding_service.py`: Ollama embedding
- `app/services/retrieval_service.py`: pgvector araması
- `app/services/llm_service.py`: Ollama chat modeli
- `app/services/rag_service.py`: RAG orkestrasyonu
- `app/services/ai_readiness_service.py`: Ollama/model kontrolü
- `app/tasks/document_tasks.py`: background ingestion

## Doğrulanmış gerçek entegrasyonlar

- Gerçek PDF upload ve background processing
- Chunk + embedding kaydı ve `ready` durumu
- Gerçek BGE-M3 semantic retrieval
- Organization izolasyonu
- Qwen3 8B ile gerçek `/ask` cevabı
- Gerçek `/ai/readiness` model kontrolü

Codex ortamında Windows temp ACL sorunu oluşursa:

```powershell
python -m pytest apps/api/tests -v -p no:cacheprovider --basetemp .codex-test-temp
```

## Bilinen eksikler

- Authentication/authorization yok; organization ID path'ten geliyor.
- Conversation create/list/detail API'leri hazır; `/ask` henüz mesajları kaydetmiyor.
- `BackgroundTasks` kalıcı job queue değildir.
- OCR ve gelişmiş PDF güvenlik kontrolleri yok.
- Local storage abstraction arkasında değil.
- Retrieval eşiği evaluation setiyle kalibre edilmedi.
- Rate limiting, structured logging, metrics ve tracing yok.
- Frontend başlamadı.

## Önerilen sonraki sıra

1. Ask endpoint'ini conversation geçmişiyle genişlet.
2. Assistant mesaj kaynaklarını detay response'una ekle.
3. Authentication ve organization membership güvenliğini ekle.
4. React + TypeScript + Vite frontend'i başlat.
5. Kalıcı worker/job queue tasarla.
6. Evaluation setiyle retrieval ve cevap kalitesini ölç.
7. Observability ve production hardening ekle.

Her feature sonunda Ruff, pytest, gerekiyorsa gerçek DB/Ollama kontrolü ve
`git status --short` çalıştırılmalıdır. Testler geçmeden commit atılmamalıdır.
