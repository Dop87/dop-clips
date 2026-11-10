import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from moviepy.editor import VideoFileClip
import shutil
import os
import random
import uuid

app = FastAPI()

PASTA_CORTES = "cortes_gerados"
os.makedirs(PASTA_CORTES, exist_ok=True)

app.mount("/cortes_gerados", StaticFiles(directory=PASTA_CORTES), name="cortes")

@app.get("/")
async def home():
    return FileResponse("index.html")

@app.post("/processar-video")
async def processar_video(
    video: UploadFile = File(...),
    duracao_corte: int = Form(60),
    formato: str = Form("original")
):
    print(f"📥 Recebendo vídeo: {video.filename}")
    
    caminho_temporario = f"temp_{uuid.uuid4().hex}.mp4"
    with open(caminho_temporario, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)
        
    cortes_finalizados = []
    
    try:
        clip = VideoFileClip(caminho_temporario)
        duracao_total = clip.duration
        
        inicio = 0
        fim = min(duracao_corte, duracao_total)
        trecho = clip.subclip(inicio, fim)
        
        print(f"🎨 Aplicando formato: {formato}")
        if formato == "vertical_bordas":
            trecho = trecho.resize(width=1080).margin(top=400, bottom=400, color=(0,0,0))
        elif formato == "corte_central":
            (w, h) = trecho.size
            trecho = trecho.crop(x1=w/2 - h*(9/32), y1=0, x2=w/2 + h*(9/32), y2=h).resize(height=1920, width=1080)
        
        nome_arquivo = f"corte_{uuid.uuid4().hex[:6]}.mp4"
        caminho_saida = os.path.join(PASTA_CORTES, nome_arquivo)
        
        trecho.write_videofile(
            caminho_saida, 
            codec="libx264", 
            audio_codec="aac", 
            fps=30,
            preset="ultrafast",
            threads=1,
            logger=None 
        )
        
        clip.close()
        trecho.close()
        os.remove(caminho_temporario)
        
        url_download = f"/cortes_gerados/{nome_arquivo}"
        
        cortes_finalizados.append({
            "url": url_download,
            "score": random.randint(75, 99)
        })
        
        return JSONResponse(content={"status": "sucesso", "cortes": cortes_finalizados})

    except Exception as e:
        print(f"❌ Erro: {e}")
        if os.path.exists(caminho_temporario):
            os.remove(caminho_temporario)
        return JSONResponse(content={"status": "erro", "mensagem": str(e)}, status_code=500)