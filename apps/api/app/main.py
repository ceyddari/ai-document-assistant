from fastapi import FastAPI

app = FastAPI(
    title="AI Document Assistant API",
    description="Şirket içi dokümanlar üzerinde kaynaklı soru-cevap API'si",
    version="0.1.0",
)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
