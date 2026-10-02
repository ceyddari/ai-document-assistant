# AI Document Assistant — Güncel Proje Bağlamı

> Son güncelleme: 2 Ekim 2026. Yeni bir sohbet bu dosyayı tamamen okumalı,
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

### Frontend

`apps/web` altında React + TypeScript + Vite uygulaması bulunur. Kayıt/giriş,
session'ın tarayıcıda tutulması, organization seçimi, PDF yükleme/listeleme,
conversation listesi ve kaynaklı soru-cevap akışları hazırdır. Varsayılan API
adresi `http://127.0.0.1:8000`; `VITE_API_URL` ile değiştirilebilir. API,
`CORS_ORIGINS` üzerinden izin verilen frontend origin'lerini sınırlar.

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
- `POST /auth/register`: kullanıcı ve sahibi olduğu organizasyonu oluşturma
- `POST /auth/login`: 24 saatlik bearer session token alma
- `GET /auth/me`: giriş yapan kullanıcı bilgisi

`/ask`, opsiyonel `conversation_id` kabul eder. Kimlik verilmezse sorudan başlık
üreterek yeni conversation oluşturur; verilirse organizasyon sınırı içinde mevcut
conversation'a user ve assistant mesajlarını ekler. Response conversation ve iki
mesajın kimliklerini döndürür. Assistant mesajlarının kullanılan chunk kaynakları
`message_sources` tablosuna kaydedilir ve conversation detayında döndürülür.

Swagger: `http://127.0.0.1:8000/docs`

## Migration zinciri

```text
45bb2d261737  enable vector extension
→ 353c369e8bd2  create organizations table
→ 49252f5931b1  create documents table
→ da06f6e62641  create document_chunks table
→ 7c2a4f8d1e90  create conversation tables
→ c84e12ab9f01  add users, organization memberships and auth sessions
```

Ana tablolar `organizations`, `users`, `organization_memberships`, `auth_sessions`,
`documents`, `document_chunks`, `conversations`, `messages` ve `message_sources`
tablolarıdır.
Retrieval sorgularında `organization_id` filtresi güvenlik sınırıdır.

Organization altındaki doküman, search, ask ve conversation endpoint'leri bearer
token ister. Kullanıcı ilgili organization için membership sahibi değilse varlığını
sızdırmamak amacıyla `404` döner. Parolalar salt'lı PBKDF2-SHA256 ile, session
token'ları yalnızca SHA-256 hash olarak PostgreSQL'de saklanır.

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

- Üyeleri mevcut organizasyonlara davet etme/yönetme endpoint'leri henüz yok.
- Session logout/revoke ve süresi dolan session temizliği henüz yok.
- `BackgroundTasks` kalıcı job queue değildir.
- OCR ve gelişmiş PDF güvenlik kontrolleri yok.
- Local storage abstraction arkasında değil.
- Retrieval eşiği evaluation setiyle kalibre edilmedi.
- Rate limiting, structured logging, metrics ve tracing yok.
- Frontend için otomatik component/e2e testleri henüz yok.

## Önerilen sonraki sıra

1. Üyelik davet/yönetimi ile logout/session revoke ekle.
2. Frontend component/e2e testlerini ve session yenileme davranışını ekle.
3. Kalıcı worker/job queue tasarla.
4. Evaluation setiyle retrieval ve cevap kalitesini ölç.
5. Observability ve production hardening ekle.

Her feature sonunda Ruff, pytest, gerekiyorsa gerçek DB/Ollama kontrolü ve
`git status --short` çalıştırılmalıdır. Testler geçmeden commit atılmamalıdır.
