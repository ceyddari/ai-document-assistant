# AI Document Assistant

PDF dokümanlarınızı yükleyip onlarla sohbet edebildiğiniz, **tamamen yerel modellerle çalışan**,
çok kiracılı (multi-tenant) bir RAG (Retrieval-Augmented Generation) uygulaması. Sorularınıza
yalnızca yüklediğiniz dokümanlara dayanarak cevap verir ve her iddianın hangi doküman, hangi
sayfadan geldiğini kaynak olarak gösterir. Hiçbir doküman içeriği dış bir servise gönderilmez.

## Öne çıkanlar

- **Kaynaklı cevaplar** – Her cevapta doküman, sayfa ve alıntı bazında atıf; yalnızca gerçekten
  atıf yapılan kaynaklar gösterilir.
- **Atıf denetimi** – Model iddiaları birebir kaynak alıntılarıyla kontrol edilir; kanıt yetersizse
  uydurmak yerine kısmi cevap verilir.
- **Hibrit arama** – pgvector ile anlamsal (cosine) arama + PostgreSQL Türkçe tam metin araması,
  skor füzyonu ve isteğe bağlı yerel reranker.
- **Sohbet bağlamı** – Takip soruları konuşma geçmişi kullanılarak bağımsız sorulara çevrilir.
- **Karşılaştırma ve özet** – Karşılaştırma sorularında her taraf için ayrı arama; seçili PDF veya
  klasör için bölüm bazlı özet.
- **Akışlı cevap** – Server-Sent Events ile cevap yazıldıkça arayüzde görünür.
- **Organizasyon izolasyonu** – Kullanıcılar yalnızca üyesi oldukları organizasyonun dokümanlarına
  ve konuşmalarına erişir.
- **Doküman yönetimi** – Klasörler, tekrar yükleme engeli (içerik hash'i), arka planda işleme,
  başarısız dokümanı yeniden işleme.
- **Güvenlik** – Parola politikası, giriş/kayıt rate limit'i, sunucu tarafında iptal edilen
  bearer session token'ları.

## Nasıl çalışır?

### 1. Doküman indeksleme

```
PDF yükleme ──► Dosya diske kaydedilir, doküman "processing" durumuna alınır
                │  (arka plan görevi, tek seferde bir doküman)
                ▼
          pypdf ile sayfa sayfa metin çıkarma (sayfa numarası korunur)
                ▼
          LangChain recursive splitter ile chunk'lara bölme
                ▼
          Ollama bge-m3 ile 1024 boyutlu embedding (batch + retry)
                ▼
          PostgreSQL / pgvector'e chunk + embedding kaydı ──► "ready"
```

### 2. Soru-cevap (RAG akışı)

```
Soru ──► Sorgu yeniden yazma (konuşma geçmişiyle bağımsız soru)
          ▼
        Hibrit arama: vektör benzerliği + Türkçe tam metin, skor füzyonu
          ▼
        (opsiyonel) CPU reranker ile ilk adayları yeniden sıralama
          ▼
        Qwen3 8B ile kaynak numaralı cevap üretimi (SSE ile akışlı)
          ▼
        Atıf ve sayısal ifade kontrolü ─► gerekirse iddia/alıntı denetimi
          ▼
        Cevap + kaynaklar konuşmaya kaydedilir, arayüzde gösterilir
```

**Uyarlanabilir kalite:** İlk kaynak belirgin biçimde öne çıktığında hızlı yol kullanılır ve cevap
yazıldıkça gösterilir. Kaynak belirsizse, soru karşılaştırma/özet ise veya taslaktaki atıflar
kontrolü geçmezse model iddiaları alıntılarla ayrıca denetler.

## Teknoloji yığını

| Katman | Kullanılanlar |
| --- | --- |
| Backend | Python 3.13, FastAPI, Pydantic, Uvicorn |
| Veritabanı | PostgreSQL 17, pgvector, SQLAlchemy 2 (async), asyncpg, Alembic |
| AI / RAG | Ollama, BGE-M3 (embedding), Qwen3 8B (LLM), LangChain, pypdf |
| Reranker (opsiyonel) | ONNX Runtime, Hugging Face tokenizers (CPU) |
| Frontend | React 19, TypeScript, Vite, react-markdown |
| Araçlar | Docker Compose, Pytest, Ruff |

## Proje yapısı

```
apps/
├── api/                    FastAPI backend
│   ├── app/
│   │   ├── api/routes/     HTTP endpoint'leri (auth, documents, folders, ask, search, ...)
│   │   ├── services/       İş mantığı: PDF parse, chunking, embedding, retrieval, RAG, LLM
│   │   ├── models/         SQLAlchemy modelleri
│   │   ├── schemas/        Pydantic istek/cevap şemaları
│   │   ├── tasks/          Arka plan doküman işleme
│   │   └── core/           Ayarlar ve rate limit
│   ├── alembic/            Veritabanı migration'ları
│   ├── scripts/            Değerlendirme ve bakım script'leri
│   └── tests/
└── web/                    React + TypeScript arayüzü
compose.yaml                PostgreSQL + API + arayüz konteynerleri
start-local.cmd             Tek tıkla kurulum ve başlatma (Windows)
```

## Kurulum

### Hızlı başlangıç

Yalnızca iki program gerekir: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
ve [Ollama](https://ollama.com). Python, Node.js veya `.env` dosyası gerekmez.

**Windows:** Projeyi indirip `start-local.cmd` dosyasına çift tıklayın. Script modelleri indirir,
veritabanı + API + arayüzü başlatır ve tarayıcıda <http://127.0.0.1:5173> adresini açar.

**macOS / Linux:**

```bash
ollama pull bge-m3 && ollama pull qwen3:8b && docker compose up -d --build
```

İlk çalıştırma modelleri (~6 GB) indirip imajları oluşturduğu için birkaç dakika sürer; sonraki
açılışlar saniyeler içinde olur.

- Arayüz: <http://127.0.0.1:5173>
- Swagger UI: <http://127.0.0.1:8000/docs>

PostgreSQL, API ve arayüz konteynerde çalışır; migration'lar açılışta otomatik uygulanır.
Ollama host makinede kalır (GPU'yu doğrudan kullanır), API ona `host.docker.internal:11434`
üzerinden bağlanır. Varsayılanları değiştirmek isterseniz `.env.example` dosyasını `.env` olarak
kopyalayıp düzenleyin. Yüklenen PDF'ler `storage/` altında kalır. Durdurmak için
`docker compose down`, loglar için `docker compose logs -f api`.

### Yerel geliştirme (hot reload)

Yalnızca kod üzerinde çalışacaksanız gerekir. Gereksinimler: Python 3.13, Node.js, Docker
Desktop ve Ollama. Önce `docker compose stop web api` ile konteyner sürümlerini durdurun.

```powershell
py -V:3.13 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -e ".\apps\api[dev]"
Copy-Item .env.example .env

ollama pull bge-m3
ollama pull qwen3:8b
docker compose up -d db
python -m alembic -c apps/api/alembic.ini upgrade head
python -m uvicorn app.main:app --app-dir apps/api --reload
```

İkinci terminalde:

```powershell
cd apps/web
npm install
npm run dev
```

`.env` Git'e eklenmez; içindeki PostgreSQL parolasını yalnızca yerel kullanım için değiştirin.

## Yapılandırma

Tüm ayarlar `.env` üzerinden yapılır (bkz. [.env.example](.env.example)). Öne çıkanlar:

| Değişken | Açıklama |
| --- | --- |
| `OLLAMA_EMBEDDING_MODEL` / `OLLAMA_LLM_MODEL` | Kullanılan modeller (`bge-m3`, `qwen3:8b`) |
| `OLLAMA_EMBEDDING_NUM_GPU` | `0` = embedding CPU'da; 8 GB GPU'da LLM ile birlikte sığması için önerilir |
| `RETRIEVAL_MIN_SIMILARITY` | Vektör aramasında minimum benzerlik eşiği |
| `RAG_ADAPTIVE_QUALITY` | `false` her soruda kapsamlı (denetimli) akışı kullanır |
| `RAG_VERIFY_CITATIONS` | Ek iddia/alıntı denetimini açar/kapatır |
| `RAG_COMPLEX_QUESTIONS` | Karşılaştırma ve özet akışlarını açar/kapatır |
| `RAG_RERANK_ENABLED` | Yerel reranker'ı etkinleştirir (önce model hazırlanmalı) |
| `MAX_UPLOAD_SIZE_MB` | Maksimum PDF boyutu |

### Opsiyonel reranker

Uyarlanabilir akışta ilk kaynak belirgin değilse hibrit aramanın ilk 8 adayını CPU'da yeniden
sıralar. Ağırlıklar bir kez indirilir ve `storage/model-cache/` altında kalır; doküman içeriği
yerelde işlenir. Model hazır değilse hibrit sıralama kullanılır, yeniden indeksleme gerekmez.

```powershell
python -m pip install -e ".\apps\api[rerank]"
python apps/api/scripts/evaluate_retrieval.py --prepare-reranker
python apps/api/scripts/evaluate_retrieval.py --compare-reranker
```

Docker imajı reranker bağımlılıklarını içerir; ağırlıkları
`docker compose run --rm --no-deps api python scripts/evaluate_retrieval.py --prepare-reranker`
ile hazırlayıp `.env` içine `RAG_RERANK_ENABLED=true` yazın ve
`docker compose up -d --build api` çalıştırın.

## API

Tüm organizasyon endpoint'leri `Authorization: Bearer <token>` ve organizasyon üyeliği gerektirir.
Tam liste ve şemalar için Swagger UI: `/docs`.

| Yöntem | Yol | Amaç |
| --- | --- | --- |
| `GET` | `/health`, `/readiness`, `/ai/readiness` | API, PostgreSQL ve Ollama/model kontrolleri |
| `POST` | `/auth/register`, `/auth/login`, `/auth/logout` | Kayıt, giriş, oturum kapatma |
| `GET` | `/auth/me` | Giriş yapan kullanıcı |
| `POST` / `GET` | `/organizations/{org}/documents` | PDF yükleme / listeleme |
| `GET` / `PATCH` / `DELETE` | `/organizations/{org}/documents/{id}` | Doküman detayı / güncelleme / silme |
| `GET` | `/organizations/{org}/documents/{id}/file` | PDF dosyasını görüntüleme |
| `POST` | `/organizations/{org}/documents/{id}/retry` | Başarısız dokümanı yeniden işleme |
| `GET` / `POST` / `DELETE` | `/organizations/{org}/folders` | Klasör yönetimi |
| `POST` | `/organizations/{org}/search` | Semantik chunk araması |
| `POST` | `/organizations/{org}/ask` | Kaynaklı RAG cevabı |
| `POST` | `/organizations/{org}/ask/stream` | Kaynaklı RAG cevabı (SSE, akışlı) |
| `POST` / `GET` | `/organizations/{org}/conversations` | Konuşma oluşturma / listeleme |
| `GET` / `PATCH` / `DELETE` | `/organizations/{org}/conversations/{id}` | Konuşma detayı / yeniden adlandırma / silme |
| `PUT` | `/organizations/{org}/conversations/{id}/documents` | Konuşmanın doküman kapsamını belirleme |
| `PUT` | `/organizations/{org}/conversations/{id}/messages/{msg}/feedback` | Cevaba 👍/👎 |

Örnek istek:

```json
{
  "question": "Projenin mimarisi nasıldır?",
  "limit": 5,
  "conversation_id": null
}
```

## Test ve kalite

```powershell
python -m ruff format --check apps/api
python -m ruff check apps/api
python -m pytest apps/api/tests -v
cd apps/web; npm run build
```

### Retrieval ve cevap değerlendirmesi

Arama ayarlarını (benzerlik eşiği, ağırlıklar, chunk biçimi) değiştirmeden önce ve sonra ölçün:

```powershell
python apps/api/scripts/evaluate_retrieval.py
python apps/api/scripts/evaluate_retrieval.py --answers --case 1 --case 2
```

Vakalar `storage/eval/retrieval_cases.json` altında durur (biçim script'in başında) ve özel
doküman içeriği taşıdığı için Git'e eklenmez. `expected` herhangi bir doğru sayfayı,
`required_sources` tamamı gerekli kaynak gruplarını, `answer_contains` beklenen ifadeleri belirtir.

Diğer script'ler:

- `scripts/reembed_documents.py` – Embedding girdisi biçimi değişince mevcut chunk'ları kaynak
  geçmişini bozmadan yeniden embed eder.
- `scripts/export_feedback.py` – Arayüzdeki 👍/👎 oylarını aday değerlendirme vakası olarak
  `storage/eval/feedback_cases.json`'a aktarır.

## Yol haritası

- Üyelik daveti ve organizasyon yönetimi
- Kalıcı background worker / job queue
- Taranmış PDF'ler için OCR ve gelişmiş PDF güvenlik kontrolleri
- Gözlemlenebilirlik ve production dağıtımı
