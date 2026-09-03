# AI Document Assistant — Project Context

> Bu dosya, projeyi yeni bir bilgisayarda ve yeni bir Codex sohbetinde kaldığı
> yerden devam ettirebilmek için hazırlanmıştır. Yeni sohbet önce bu dosyanın
> tamamını, ardından gerçek repository durumunu (`git status`, dosyalar ve testler)
> okumalıdır. Bu dosyadaki komutlar ağırlıklı olarak Windows PowerShell içindir.

## 1. Projenin amacı

Şirket çalışanlarının PDF/doküman yükleyip doğal dilde soru sorabildiği, RAG
(Retrieval-Augmented Generation) tabanlı şirket içi doküman asistanı geliştiriliyor.

Örnek sorular:

- “Yıllık izin prosedürü nedir?”
- “Bu dokümana göre satın alma talebi nasıl oluşturuluyor?”
- “Bu sözleşmedeki fesih şartı ne?”

Sistem yalnızca cevap üretmeyecek; cevabın altında yararlanılan dokümanı, sayfa
numarasını ve ilgili metin parçasını da gösterecek.

Bu bir öğrenme ve portföy projesidir. Kod yazılırken yalnızca komut verilmemeli;
her dosyanın, katmanın ve teknik kararın amacı kullanıcıya açıklanmalıdır. Adımlar
küçük tutulmalı, her adım lint/test/migration ile doğrulandıktan sonra devam
edilmelidir.

## 2. Repository ve yerel ortam

- Proje adı: `ai-document-assistant`
- Windows yolu:
  `C:\Users\ceydanur.duman\Desktop\projects\ai-document-assistant`
- GitHub:
  `https://github.com/ceyddari/ai-document-assistant.git`
- Ana branch: `main`
- Son commit: `c349cfb chore: configure document uploads`
- Python proje sürümü: `3.13.15`
- Sistem genelindeki Python: `3.14.7`
- Sanal ortam: repository kökündeki `.venv`
- PostgreSQL host portu: `5434`
- PostgreSQL container portu: `5432`

Bilgisayar/donanım:

- RAM: 32 GB (Windows yaklaşık 31,3 GB gösteriyor)
- GPU: NVIDIA GeForce RTX 5070 Laptop GPU
- VRAM: yaklaşık 8 GB (`nvidia-smi`: 8151 MiB)
- Entegre GPU: AMD Radeon 610M
- NVIDIA/CUDA kurulumu çalışıyor.

Python 3.13 seçilmesinin nedeni, proje bağımlılıklarının Python 3.14'e göre daha
oturmuş uyumluluğa sahip olmasıdır. `pyproject.toml` şu aralığı zorunlu tutar:

```toml
requires-python = ">=3.13,<3.14"
```

## 3. Hedef teknoloji yığını

### Backend

- Python 3.13
- FastAPI
- Uvicorn
- SQLAlchemy 2 async
- `asyncpg`
- Pydantic Settings
- Alembic
- `aiofiles`
- `python-multipart`
- Pytest + pytest-asyncio
- Ruff (lint + format + import düzenleme)

### Veritabanı ve dosya saklama

- PostgreSQL 17
- pgvector 0.8.6
- Docker Compose
- İlk sürümde yüklenen dosyalar yerel `storage/` dizininde
- Dosyanın kendisi PostgreSQL'e yazılmıyor; PostgreSQL dosya metadata'sını tutuyor.

### Frontend (henüz başlanmadı)

- React
- TypeScript
- Vite
- React Router
- TanStack Query
- Tailwind CSS
- Gerekirse shadcn/ui
- HTTP istemcisi olarak `fetch` veya Axios

Planlanan ekranlar:

- Doküman listesi
- PDF/doküman yükleme
- Doküman işleme durumları
- Kaynaklı sohbet/soru-cevap ekranı
- Cevabın yanında kaynak doküman, sayfa ve ilgili metin paneli
- Organizasyon ve kullanıcı alanları

### Yerel AI modelleri için mevcut karar

API maliyetinden kaçınmak ve dokümanları yerelde tutmak için hedef seçim:

- Model çalıştırıcı: Ollama
- Cevap üreten LLM: `qwen3:8b`
- Embedding modeli: `bge-m3`
- BGE-M3 embedding boyutu: 1024

Planlanan kurulum (henüz yapılmadı):

```powershell
ollama pull qwen3:8b
ollama pull bge-m3
```

Donanım `qwen3:8b` ve BGE-M3 için uygundur. Gerekirse performans için
`qwen3:4b` kullanılabilir.

Alternatif bulut seçimi konuşuldu ancak entegre edilmedi:

- LLM: OpenAI `gpt-5.6-luna`
- Embedding: `text-embedding-3-small`

Sağlayıcı değiştirilebilecek şekilde servis arayüzleri tasarlanmalıdır. Ancak
mevcut yön yerel Ollama'dır. Kendi modelimizi sıfırdan eğitmeyeceğiz; dokümana
özel bilgi RAG ile verilecek. Fine-tuning ilk sürümde gerekli değildir.

## 4. RAG mimarisi

RAG iki ana akıştan oluşur.

### 4.1 Doküman alma ve indeksleme (ingestion/indexing)

```text
PDF yükleme
  -> dosyayı storage/ altında saklama
  -> documents tablosuna pending kayıt
  -> PDF'den sayfa numarası korunarak metin çıkarma
  -> metni anlamlı chunk'lara bölme
  -> BGE-M3 ile her chunk için embedding üretme
  -> chunk + metadata + vector değerini pgvector'a kaydetme
  -> document durumunu ready yapma
```

Başlangıç chunk parametreleri kesinleşmemiş önerilerdir:

- 500–800 token chunk boyutu
- 80–150 token overlap

Sayfa numarası mutlaka korunmalıdır; kaynak göstermek için gereklidir. Metin
katmanı olmayan taranmış PDF'ler için OCR daha sonraki aşamadır.

### 4.2 Soru-cevap

```text
Kullanıcı sorusu
  -> aynı embedding modeliyle soru vektörü
  -> organization_id filtresiyle pgvector benzerlik araması
  -> en ilgili chunk'ları seçme
  -> soru + chunk'ları LLM prompt'una bağlam olarak verme
  -> yalnızca kaynaklara dayalı cevap üretme
  -> cevap + document/page/chunk kaynaklarını frontend'e döndürme
```

RAG terimleri:

- Retrieval: pgvector'dan ilgili parçaları bulma
- Augmented: parçaları LLM bağlamına ekleme
- Generation: LLM'in kaynaklara dayanarak cevap üretmesi

LLM PDF'yi aramaz ve veritabanına doğrudan bağlanmaz. Arama bizim retrieval
servisimizde yapılır; LLM yalnızca seçilmiş kaynakları okuyup cevap yazar.

Doküman ve soru embedding'leri aynı modelle üretilmelidir. `bge-m3` kullanıldığı
için gelecekteki vector sütunu `vector(1024)` olmalıdır. Embedding modeli
değiştirilirse boyut ve mevcut vektörlerin yeniden üretilmesi konusu ele alınmalıdır.

## 5. Çok kiracılı (multi-tenant) karar

`organizations` tablosu projeye gerçek hayata yakın veri izolasyonu sağlamak için
eklendi. İleride `users`, `documents`, `document_chunks`, `conversations` ve
benzeri tablolar `organization_id` ile şirkete bağlanacak.

Her retrieval sorgusunda organizasyon filtresi zorunlu olmalıdır:

```sql
WHERE organization_id = :current_organization_id
```

Bir şirketin kullanıcısı başka şirketin dokümanlarını veya chunk'larını asla
görememelidir. Bu yalnızca performans filtresi değil, güvenlik sınırıdır.

## 6. Mevcut klasör yapısı

```text
ai-document-assistant/
├── .env                       # Yerel secret/ayarlar, Git'e girmez
├── .env.example               # Güvenli örnek ayarlar
├── .gitignore
├── compose.yaml
├── README.md
├── PROJECT_CONTEXT.md         # Bu dosya
├── storage/
│   └── .gitkeep               # Gerçek yüklemeler ignore edilir
├── docs/                      # Şimdilik boş
└── apps/
    ├── web/                   # React frontend henüz kurulmadı
    └── api/
        ├── pyproject.toml
        ├── alembic.ini
        ├── alembic/
        │   ├── env.py
        │   ├── script.py.mako
        │   └── versions/
        │       ├── 45bb2d261737_enable_vector_extension.py
        │       ├── 353c369e8bd2_create_organizations_table.py
        │       └── 49252f5931b1_create_documents_table.py
        ├── app/
        │   ├── main.py
        │   ├── api/
        │   │   └── routes/          # Route dosyaları henüz yok
        │   ├── core/
        │   │   └── config.py
        │   ├── db/
        │   │   ├── base.py
        │   │   └── session.py
        │   ├── models/
        │   │   ├── organization.py
        │   │   └── document.py
        │   ├── schemas/
        │   │   └── document.py      # Henüz commit edilmedi
        │   └── services/
        │       └── document_service.py # Henüz commit edilmedi
        └── tests/
            ├── test_health.py
            ├── test_readiness.py
            └── test_document_service.py # Henüz commit edilmedi
```

Katmanların sorumluluğu:

- `api/routes`: HTTP request/response, status code ve hata eşleme
- `schemas`: Pydantic API giriş/çıkış sözleşmeleri
- `services`: İş kuralları ve akış yönetimi
- `models`: SQLAlchemy tablo modelleri
- `db`: Engine/session altyapısı
- `core`: Ortak yapılandırma

## 7. Docker ve PostgreSQL

`compose.yaml` veritabanı servisini şu image ile çalıştırır:

```text
pgvector/pgvector:0.8.6-pg17-trixie
```

Port eşlemesi:

```text
Windows host 5434 -> container 5432
```

5432 host portu başka projelerde kullanıldığı için 5434 seçildi. Container
içinde PostgreSQL yine standart 5432 portunda çalışır.

Temel komutlar:

```powershell
docker compose up -d db
docker compose ps
docker compose exec db pg_isready -U app_user -d ai_document_assistant
```

Buradaki `docker compose up -d` içindeki `-d`, detached/background modudur.
`psql -d ai_document_assistant` içindeki `-d` ise database adını belirtir.

Önceden karşılaşılan `Bind for 0.0.0.0:5432 failed: port is already allocated`
hatası host portunun 5434 yapılmasıyla çözüldü. Doğru çıktı:

```text
0.0.0.0:5434->5432/tcp
```

Alembic'te `ConnectionRefusedError [WinError 1225]` görülürse çoğunlukla Docker
container kapalıdır; önce `docker compose up -d db` çalıştırılmalıdır.

## 8. Ortam değişkenleri

`.env.example` mevcut içeriği:

```env
POSTGRES_DB=ai_document_assistant
POSTGRES_USER=app_user
POSTGRES_PASSWORD=change_me_local_only
POSTGRES_HOST=localhost
POSTGRES_PORT=5434
STORAGE_DIRECTORY=storage/documents
MAX_UPLOAD_SIZE_MB=10
```

Yeni bilgisayarda bunu `.env` olarak kopyala ve yerel parolayı değiştir:

```powershell
Copy-Item -LiteralPath '.env.example' -Destination '.env'
```

`.env` Git'e gönderilmez. API anahtarları veya gerçek parolalar kaynak koda ve
`.env.example` dosyasına yazılmamalıdır.

`Settings` şu değerleri okur:

- PostgreSQL bağlantı bilgileri
- `storage_directory` (varsayılan `storage/documents`)
- `max_upload_size_mb` (varsayılan 10 MB)
- `max_upload_size_bytes` hesaplanan property

Not: `storage_directory` şu anda relative path'tir ve uygulamanın repository
kökünden çalıştırıldığı varsayılır. İleride Docker/production için mutlak bir
storage root veya uygulama köküne göre güvenli path çözümleme eklenmelidir.

## 9. Veritabanı modelleri

### 9.1 Organization

`organizations` alanları:

- `id`: UUID primary key
- `name`: şirket adı, maksimum 255
- `slug`: benzersiz, maksimum 100
- `created_at`: timezone-aware, DB `now()` varsayılanı

### 9.2 Document

`documents` alanları:

- `id`: UUID primary key
- `organization_id`: `organizations.id` foreign key
- `ondelete="CASCADE"`: organizasyon silinirse doküman kayıtları silinir
- `original_filename`: kullanıcının yüklediği dosya adı
- `stored_filename`: UUID tabanlı benzersiz sunucu dosya adı
- `storage_path`: disk üzerindeki iç yol
- `content_type`: şimdilik `application/pdf`
- `size_bytes`: dosya boyutu, negatif olamaz
- `status`: `pending`, `processing`, `ready`, `failed`
- `error_message`: işleme hatası
- `created_at`, `updated_at`

`status`, PostgreSQL native enum yerine `native_enum=False` ile kontrol kurallı
metin olarak tutuluyor. Bu, ileride yeni durum eklemeyi kolaylaştırır.

İndeksler:

- `documents.organization_id`
- `documents.status`

Kısıtlar:

- `stored_filename` unique
- `size_bytes >= 0`
- organization foreign key

Not: `updated_at` için SQLAlchemy `onupdate=func.now()` kullanılıyor. ORM dışı ham
SQL güncellemelerinde bu otomatik davranış garanti edilmez; gerekirse DB trigger
veya açık timestamp güncellemesi düşünülmelidir.

## 10. Alembic migration zinciri

Migration sırası:

```text
45bb2d261737  enable vector extension
    -> 353c369e8bd2  create organizations table
        -> 49252f5931b1  create documents table (head)
```

Komutlar:

```powershell
python -m alembic -c apps/api/alembic.ini current
python -m alembic -c apps/api/alembic.ini upgrade head
python -m alembic -c apps/api/alembic.ini revision --autogenerate -m "message"
```

Alembic migration ürettikten sonra dosya mutlaka gözle incelenmeli, sonra Ruff
uygulanmalıdır. Alembic'in ürettiği `typing.Union`/import biçimi Ruff'un Python
3.13 kurallarıyla otomatik düzeltilmiştir.

`alembic/env.py`, Alembic metadata'ya yükleyebilsin diye modelleri açıkça import
eder:

```python
from app.models import Document, Organization
model_registry = (Document, Organization)
target_metadata = Base.metadata
```

## 11. Mevcut API endpoint'leri

### `GET /health`

Uygulamanın çalıştığını kontrol eder:

```json
{"status": "ok"}
```

### `GET /readiness`

`SELECT 1` ile PostgreSQL bağlantısını kontrol eder:

- Başarılı: `200 {"status": "ready"}`
- DB yok: `503 {"detail": "Database is unavailable"}`

Kök `/` endpoint'i yoktur. Tarayıcıda `http://127.0.0.1:8000/` açıldığında
`{"detail":"Not Found"}` görülmesi normaldir. Swagger:

```text
http://127.0.0.1:8000/docs
```

Çalıştırma:

```powershell
python -m uvicorn app.main:app --app-dir apps/api --reload
```

## 12. Doküman yükleme özelliğinin mevcut çalışma durumu

Bu bölümdeki dosyalar diskte var ancak henüz commit edilmemiştir.

### 12.1 `DocumentResponse`

Frontend'e dönecek alanları tanımlar:

- `id`
- `organization_id`
- `original_filename`
- `content_type`
- `size_bytes`
- `status`
- `error_message`
- `created_at`
- `updated_at`

Güvenlik/soyutlama nedeniyle `stored_filename` ve `storage_path` response'a
konulmadı; bunlar sunucunun iç ayrıntılarıdır.

### 12.2 `create_document` servisi

`app/services/document_service.py` şunları yapıyor:

1. `Path(file.filename).name` ile path traversal girişimini temizler.
2. `.pdf` uzantısını kontrol eder.
3. MIME türünü `application/pdf` olarak kontrol eder.
4. Organizasyonun DB'de varlığını kontrol eder.
5. `storage_directory` klasörünü oluşturur.
6. UUID tabanlı benzersiz `.pdf` dosya adı üretir.
7. Dosyayı `aiofiles` ile 1 MB bloklar halinde yazar.
8. İlk blokta `%PDF-` imzasını kontrol eder.
9. Boyut sınırını uygular.
10. Başarılıysa `Document` kaydı oluşturur ve commit eder.
11. Dosya veya DB hatasında yarım/sahipsiz dosyayı siler.

Servis exception'ları:

- `OrganizationNotFoundError`
- `InvalidPdfError`
- `DocumentTooLargeError`

Temel `%PDF-` kontrolü gerçek PDF parser doğrulamasının yerini tutmaz. İleride
PyMuPDF ile açma/parsing doğrulaması eklenmelidir. MIME header da istemci
tarafından sahte gönderilebilir; imza + parser birlikte kullanılmalıdır.

Potansiyel iyileştirme: uzantı/MIME/organizasyon kontrolleri sırasında erken
exception oluşursa servis `UploadFile.close()` çağrısına ulaşmıyor. FastAPI request
yaşam döngüsü dosyayı kapatsa da servis fonksiyonu kendi başına daha güçlü bir
`finally` ile tüm yolları kapatacak şekilde refactor edilebilir.

### 12.3 Servis testleri

`test_document_service.py` dört senaryoyu kapsar:

- Geçerli PDF kaydedilir ve DB işlemleri çağrılır.
- PDF imzası olmayan içerik reddedilir ve yarım dosya kalmaz.
- Boyut sınırını aşan dosya reddedilir ve yarım dosya kalmaz.
- Bulunmayan organizasyon reddedilir.

Testlerde:

- `tmp_path`: gerçek `storage/` yerine geçici klasör
- `AsyncMock`: gerçek PostgreSQL yerine sahte `AsyncSession`
- `BytesIO`: bellekte dosya benzeri nesne

Önceden testte `assert not tmp_path.exists()` kullanıldığı için bir failure oluştu.
Pytest `tmp_path` klasörünü testten önce yarattığından doğru assertion şu oldu:

```python
assert list(settings.storage_directory.iterdir()) == []
```

31 Ağustos 2026 doğrulaması:

- Toplam 7 test geçti.
- `ruff check apps/api`: geçti.
- `ruff format --check apps/api`: test dosyasının sonunda bir format farkı buldu.
  Sıradaki ilk komut `python -m ruff format apps/api` olmalıdır.

Codex sandbox'ında standart Windows temp dizinine erişim engeli görülebilir. Bu
uygulama hatası değildir. Alternatif doğrulama örneği:

```powershell
python -m pytest apps/api/tests -v -p no:cacheprovider --basetemp .test-temp
```

Kullanıcının normal PowerShell ortamında standart pytest komutu çalışmıştır.

## 13. Git durumu ve commit geçmişi

Mevcut commit'ler (eskiden yeniye):

```text
fda992e chore: initialize FastAPI project
1aefca1 chore: add PostgreSQL pgvector service
877a6a4 feat: add async database connectivity
d8be00d test: add readiness endpoint coverage
8f5cd76 feat: add Alembic migration infrastructure
133df34 feat: add organization model
fc268e4 feat: add document model
c349cfb chore: configure document uploads
```

31 Ağustos 2026 itibarıyla commit edilmemiş değişiklikler:

```text
M  apps/api/app/core/config.py
?? apps/api/app/api/
?? apps/api/app/schemas/
?? apps/api/app/services/
?? apps/api/tests/test_document_service.py
```

Bu dosyalar kullanıcıya aittir; yeni sohbet bunları silmemeli veya resetlememelidir.
İlk olarak format/test çalıştırılmalı, sonra upload route'u ve route testleri
tamamlanarak anlamlı bir feature commit'i atılmalıdır.

## 14. Çözülen teknik problemler

### PowerShell sanal ortam aktivasyonu

PowerShell script execution policy nedeniyle `Activate.ps1 cannot be loaded`
hatası alındı. Oturum bazlı çözüm:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Kalıcı sistem ayarı değiştirilmedi.

### Python 3.14 yerine proje Python 3.13

Sistemde `python --version` 3.14 gösterse de proje `.venv` Python 3.13 ile
oluşturuldu:

```powershell
py -V:3.13 -m venv .venv
```

Aktif venv kontrolü:

```powershell
python --version
Get-Command python
python -m pip --version
```

Kaynak `.venv\Scripts\python.exe` olmalıdır.

### Editable install ve paket discovery

Alembic eklendikten sonra setuptools şu hatayı verdi:

```text
Multiple top-level packages discovered in a flat-layout: ['app', 'alembic']
```

`pyproject.toml` içine açık paket keşfi eklenerek çözüldü:

```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["app*"]
exclude = ["alembic*", "tests*"]
```

Editable kurulum:

```powershell
python -m pip install -e ".\apps\api[dev]"
```

Editable kurulum, kaynak dosyaları site-packages içine kopyalamak yerine projeyi
geliştirme paketi olarak bağlar; kod değişiklikleri yeniden kurulum gerektirmez.
`*.egg-info` paket metadata'sıdır ve Git'te ignore edilir.

### Ruff ve Alembic tarafından üretilen kod

Alembic'in otomatik migration dosyalarında import sırası ve eski `Union` syntax'ı
Ruff uyarıları oluşturdu. Güvenli çözüm:

```powershell
python -m ruff check apps/api --fix
python -m ruff format apps/api
```

### Cache ve metadata klasörleri

- `__pycache__` / `.pyc`: Python bytecode cache
- `.pytest_cache`: pytest çalışma cache'i
- `.ruff_cache`: Ruff analiz cache'i
- `.egg-info`: kurulu Python paketinin metadata'sı

Bunlar kaynak kod değildir, yeniden üretilebilir ve `.gitignore` içindedir.

### VS Code formatter kararı

Ruff VS Code extension kullanılıyor. Önerilen ayar:

```json
{
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": "explicit",
      "source.organizeImports.ruff": "explicit"
    }
  }
}
```

Ruff format/stil/import sorunlarını otomatik düzeltebilir; syntax veya mantık
hatalarını otomatik çözmesi garanti değildir. Terminal lint ve testleri devam eder.

## 15. Yeni bilgisayarda kurulum ve çalıştırma

Gerekenler:

- Git
- VS Code
- Python 3.13
- Docker Desktop + Docker Compose
- İleride Ollama

Repository'yi klonladıktan sonra:

```powershell
cd C:\istenen\yol\ai-document-assistant
py -V:3.13 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\apps\api[dev]"
Copy-Item -LiteralPath '.env.example' -Destination '.env'
```

`.env` içindeki yerel PostgreSQL parolasını ayarla. Ardından:

```powershell
docker compose up -d db
docker compose ps
python -m alembic -c apps/api/alembic.ini upgrade head
python -m pytest apps/api/tests -v
python -m ruff check apps/api
python -m uvicorn app.main:app --app-dir apps/api --reload
```

API:

```text
http://127.0.0.1:8000
http://127.0.0.1:8000/docs
```

## 16. Sıradaki kesin işler

Yeni sohbet aşağıdaki sırayla devam etmelidir.

### 16.1 Mevcut çalışma alanını doğrula

```powershell
git status --short
python -m ruff format apps/api
python -m ruff check apps/api
python -m pytest apps/api/tests -v
```

Beklenti: 7 test geçer ve Ruff temiz olur.

### 16.2 Upload route'u ekle

Hedef endpoint:

```http
POST /organizations/{organization_id}/documents
Content-Type: multipart/form-data
```

Planlanan dosya:

```text
apps/api/app/api/routes/documents.py
```

Route sorumlulukları:

- `UploadFile` almak
- `AsyncSession` dependency almak
- `Settings` dependency almak
- `create_document` servisini çağırmak
- `DocumentResponse` döndürmek
- HTTP 201 dönmek
- Exception eşlemeleri:
  - organizasyon yok -> 404
  - geçersiz PDF -> 400 veya 415 (bir karar verilip test edilmeli)
  - büyük dosya -> 413
  - beklenmeyen DB hatası -> güvenli 500

Route, `main.py` içine doğrudan yığılmamalı; `APIRouter` ile kaydedilmelidir.
Gerekirse DB session type alias `app/api/dependencies.py` içine taşınmalıdır.

### 16.3 Upload route testleri

Gerçek disk ve DB'ye bağımlılığı azaltmak için servis mock'lanabilir. Testler en
az şunları kapsamalıdır:

- Başarılı yükleme -> 201 + response şeması
- Organizasyon yok -> 404
- Geçersiz PDF -> belirlenen 4xx
- Büyük dosya -> 413

### 16.4 Manuel entegrasyon testi

Route gerçek DB ile denenmeden önce bir organization kaydı gerekir. Henüz
organization oluşturma endpoint'i veya seed mekanizması yoktur. Seçenekler:

- küçük bir organization creation endpoint'i eklemek,
- geliştirme seed script'i yazmak,
- geçici olarak kontrollü SQL insert kullanmak.

Kalıcı yaklaşım kararlaştırılmalıdır; UUID elle uydurulup FK atlanmamalıdır.

### 16.5 Feature commit

Upload şeması + servis + route + testler tamamlanınca:

```powershell
git status --short
git add <yalnızca bu özelliğe ait dosyalar>
git commit -m "feat: add document upload endpoint"
git push origin main
```

`.env`, `storage` içindeki gerçek dosyalar, cache ve `.venv` staging'e alınmamalıdır.

## 17. Sonraki büyük geliştirme sırası

Upload endpoint'inden sonra önerilen sıra:

1. Doküman listeleme ve detay endpoint'leri
2. Organization geliştirme verisi/endpoint'i
3. PDF parser (PyMuPDF düşünülüyor)
4. Sayfa bazlı metin çıkarma
5. `document_chunks` modeli ve migration
6. pgvector `vector(1024)` sütunu
7. Chunking servisi
8. Ollama kurulumu ve health check
9. BGE-M3 embedding servisi
10. Ingestion pipeline ve document status geçişleri
11. Benzerlik araması/retrieval servisi
12. Qwen3 8B LLM servisi
13. Prompt ve yapılandırılmış kaynak/citation çıktısı
14. RAG orchestration servisi
15. Conversation/message/source tabloları ve API'leri
16. Kimlik doğrulama ve organization yetkilendirmesi
17. React + TypeScript frontend
18. Docker ile API/web/worker paketleme
19. OCR, background job/queue, gözlemlenebilirlik ve production güvenliği

LangChain başlangıçta zorunlu değildir. Temel RAG akışının mantığını öğrenmek için
ilk sürümün servisleri doğrudan yazılabilir; ihtiyaç belirginleşirse LangChain daha
sonra eklenebilir.

## 18. Bilinen eksikler ve teknik borçlar

- `README.md` mevcut durumu geriden takip ediyor; PostgreSQL/pgvector yapılmış
  olmasına rağmen checklist eski. Ayrıca backend çalıştırma code fence'i eksik
  kapanmış görünüyor. Upload feature commit'inden sonra güncellenmeli.
- Upload route henüz yok; servis yalnızca Python içinden çağrılabilir.
- Organization creation/seed mekanizması yok.
- Doküman parsing/chunking/embedding/retrieval/LLM yok.
- `document_chunks` tablosu yok.
- Ollama ve modeller henüz projeye entegre değil.
- Frontend kurulmadı.
- Authentication/authorization henüz yok.
- Local disk storage production için abstraction arkasına alınmalı; ileride S3
  benzeri object storage düşünülebilir.
- İşleme uzun süreceği için ingestion sonunda HTTP request içinde yapılmamalı;
  background task veya job queue tasarlanmalı.
- Upload'ta virüs tarama, gelişmiş MIME kontrolü, şifreli PDF, sayfa sınırı ve
  zip-bomb benzeri güvenlik kontrolleri ileride eklenmeli.
- Organizasyon izolasyonu her repository/retrieval sorgusunda test edilmelidir.

## 19. Çalışma biçimi ve kullanıcı tercihleri

- Kullanıcı komutları kendi terminalinde çalıştırarak öğrenmek istiyor.
- Her adımın “neden”i açıklanmalı; yalnızca kopyalanacak kod verilmemeli.
- Bir seferde kontrollü sayıda adım verilmeli.
- Her özellikten sonra Ruff, pytest, migration/DB doğrulaması ve `git status`
  kontrol edilmeli.
- Kullanıcının mevcut değişiklikleri korunmalı; dirty worktree resetlenmemeli.
- Gerçek secret değerleri yanıtta veya commit'te paylaşılmamalı.
- Commit'ler küçük ve anlamlı tutulmalı.

## 20. Yeni Codex sohbeti için başlangıç talimatı

Yeni sohbette şu şekilde başlanabilir:

> `PROJECT_CONTEXT.md` dosyasını tamamen oku. Ardından repository'de `git status
> --short`, son commitler, ilgili kaynak dosyalar ve testleri kontrol et. Dosyadaki
> bilgileri körü körüne varsayma; gerçek çalışma alanıyla karşılaştır. Kullanıcının
> commit edilmemiş değişikliklerini koru. Önce mevcut 7 testi ve Ruff format/check'i
> doğrula; sonra `POST /organizations/{organization_id}/documents` endpoint'ini
> öğretici ve küçük adımlarla geliştirmeye devam et.

