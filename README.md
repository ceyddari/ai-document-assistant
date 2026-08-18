# AI Document Assistant

Şirket içi PDF ve DOCX dokümanlarına doğal dilde soru sorulmasını sağlayan,
RAG tabanlı doküman asistanı.

## Hedef

Kullanıcıların yüklediği dokümanlardan ilgili bölümleri bulmak, bu bölümleri
bir dil modeline bağlam olarak vermek ve kullanılan kaynakları göstererek
cevap üretmek.

## Teknolojiler

- React ve TypeScript
- Python ve FastAPI
- PostgreSQL ve pgvector
- OpenAI veya değiştirilebilir LLM sağlayıcısı
- Docker Compose

## Mevcut durum

- [x] FastAPI proje iskeleti
- [x] Health-check endpoint
- [ ] PostgreSQL ve pgvector
- [ ] Doküman yükleme
- [ ] Embedding oluşturma
- [ ] RAG soru-cevap
- [ ] React kullanıcı arayüzü

## Backend'i çalıştırma

Sanal ortamı etkinleştir:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1