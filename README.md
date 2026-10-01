# AI Document Assistant

Şirket içi PDF dokümanları üzerinde kaynak göstererek soru-cevap üreten, yerel
modellerle çalışan çok kiracılı bir RAG uygulaması.

## Güncel özellikler

- PDF yükleme, listeleme ve detay API'leri
- Sayfa numarasını koruyan PDF metin çıkarma
- LangChain recursive text chunking
- Ollama `bge-m3` ile 1024 boyutlu embedding
- PostgreSQL 17 + pgvector cosine similarity araması
- Organizasyon bazlı veri izolasyonu
- Arka planda doküman indeksleme ve durum yönetimi
- Ollama `qwen3:8b` ile kaynak-temelli cevap üretimi
- Cevapla birlikte doküman, sayfa, chunk ve similarity kaynakları
- PostgreSQL ve AI readiness endpoint'leri

## Teknoloji yığını

- Python 3.13, FastAPI, Pydantic
- SQLAlchemy 2 async, asyncpg, Alembic
- PostgreSQL 17, pgvector
- Ollama, BGE-M3, Qwen3 8B
- pypdf, LangChain text splitters
- Pytest, pytest-asyncio, Ruff
- Docker Compose

## Yerel kurulum

Gereksinimler: Python 3.13, Docker Desktop ve Ollama.

```powershell
py -V:3.13 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -e ".\apps\api[dev]"
Copy-Item .env.example .env
```

`.env` içindeki PostgreSQL parolasını yalnızca yerel kullanım için değiştirin.
Bu dosya Git'e eklenmez.

```powershell
ollama pull bge-m3
ollama pull qwen3:8b
docker compose up -d db
python -m alembic -c apps/api/alembic.ini upgrade head
python -m uvicorn app.main:app --app-dir apps/api --reload
```

Swagger UI: <http://127.0.0.1:8000/docs>

## Önemli endpoint'ler

| Yöntem | Yol | Amaç |
| --- | --- | --- |
| `GET` | `/health` | API process kontrolü |
| `GET` | `/readiness` | PostgreSQL bağlantı kontrolü |
| `GET` | `/ai/readiness` | Ollama ve gerekli model kontrolü |
| `POST` | `/organizations/{organization_id}/documents` | PDF yükleme |
| `GET` | `/organizations/{organization_id}/documents` | Doküman listesi |
| `GET` | `/organizations/{organization_id}/documents/{document_id}` | Doküman detayı |
| `POST` | `/organizations/{organization_id}/search` | Semantik chunk araması |
| `POST` | `/organizations/{organization_id}/ask` | Kaynaklı RAG cevabı |

Örnek soru-cevap isteği:

```json
{
  "question": "Sürpriz Kasa projesinin mimarisi nasıldır?",
  "limit": 5
}
```

## Kalite kontrolleri

```powershell
python -m ruff format --check apps/api
python -m ruff check apps/api
python -m pytest apps/api/tests -v
```

Gerçek yüklenen PDF'ler `storage/documents/`, secret değerleri `.env` altında
tutulur ve Git tarafından ignore edilir.

## Sonraki aşamalar

- Conversation ve message kalıcılığı
- Authentication ve organization yetkilendirmesi
- React + TypeScript + Vite frontend
- Kalıcı background worker/job queue
- OCR ve gelişmiş PDF güvenlik kontrolleri
- Gözlemlenebilirlik, rate limiting ve production dağıtımı
