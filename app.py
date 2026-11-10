import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont
import numpy as np
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
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

# Função auxiliar para desenhar texto usando Pillow (Evita o problema do ImageMagick)
def criar_imagem_texto(texto, largura=1080, altura=200):
    # Cria uma imagem transparente
    img = PIL.Image.new('RGBA', (largura, altura), (255, 255, 255, 0))
    d = PIL.ImageDraw.Draw(img)
    
    # Tenta usar a fonte padrão (Arial) ou cai para a fonte básica
    try:
        font = PIL.ImageFont.truetype("arial.ttf", 80)
    except IOError:
        font = PIL.ImageFont.load_default()
    
    # Obtém o tamanho do texto para centralizar (método antigo para compatibilidade Pillow 9.5)
    text_width, text_height = d.textsize(texto, font=font) if hasattr(d, 'textsize') else (400, 100)
    
    x = (largura - text_width) / 2
    y = (altura - text_height) / 2
    
    # Desenha borda preta grossa para destaque
    borda = 4
    for offset_x in [-borda, 0, borda]:
        for offset_y in [-borda, 0, borda]:
            d.text((x + offset_x, y + offset_y), texto, fill="black", font=font)
    
    # Desenha texto branco principal
    d.text((x, y), texto, fill="white", font=font)
    
    return np.array(img)

@app.post("/processar-video")
async def processar_video(
    video: UploadFile = File(...),
    duracao_corte: int = Form(60),
    formato: str = Form("original"),
    tipo_texto: str = Form("nenhum"), # nenhum, fixo, sequencial
    texto_usuario: str = Form("")
):
    print(f"📥 Recebendo vídeo: {video.filename}")
    caminho_temporario = f"temp_{uuid.uuid4().hex}.mp4"
    with open(caminho_temporario, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)
        
    cortes_finalizados = []
    
    try:
        clip = VideoFileClip(caminho_temporario)
        duracao_total = clip.duration
        print(f"⏱️ Vídeo de {duracao_total}s. Fatiando em {duracao_corte}s...")
        
        # LAÇO DE REPETIÇÃO: Fatiando o vídeo inteiro
        inicio = 0
        numero_corte = 1
        
        while inicio < duracao_total:
            fim = min(inicio + duracao_corte, duracao_total)
            
            # Se o último corte tiver menos de 5 segundos (uma "rebarba"), ignoramos
            if (fim - inicio) < 5:
                break
                
            trecho = clip.subclip(inicio, fim)
            
            # Aplica o Formato
            if formato == "vertical_bordas":
                trecho = trecho.resize(width=1080).margin(top=400, bottom=400, color=(0,0,0))
            elif formato == "corte_central":
                (w, h) = trecho.size
                trecho = trecho.crop(x1=w/2 - h*(9/32), y1=0, x2=w/2 + h*(9/32), y2=h).resize(height=1920, width=1080)
            
            # Aplica o Texto (se solicitado)
            (w, h) = trecho.size
            texto_final = ""
            
            if tipo_texto == "fixo" and texto_usuario:
                texto_final = texto_usuario
            elif tipo_texto == "sequencial" and texto_usuario:
                texto_final = f"{texto_usuario} {numero_corte}"
                
            if texto_final:
                print(f"✍️ Adicionando texto: '{texto_final}' no corte {numero_corte}")
                # Cria a imagem do texto
                array_imagem_texto = criar_imagem_texto(texto_final, largura=w, altura=250)
                # Transforma a imagem num clip de vídeo estático com fundo transparente
                txt_clip = ImageClip(array_imagem_texto).set_duration(trecho.duration).set_position(('center', 100))
                # Junta o texto por cima do vídeo
                trecho = CompositeVideoClip([trecho, txt_clip])
            
            # Salva
            nome_arquivo = f"corte_{numero_corte}_{uuid.uuid4().hex[:4]}.mp4"
            caminho_saida = os.path.join(PASTA_CORTES, nome_arquivo)
            
            print(f"⚙️ Renderizando corte {numero_corte}...")
            trecho.write_videofile(
                caminho_saida, codec="libx264", audio_codec="aac", 
                fps=30, preset="ultrafast", threads=1, logger=None
            )
            trecho.close()
            
            cortes_finalizados.append({
                "url": f"/cortes_gerados/{nome_arquivo}",
                "score": random.randint(75, 99),
                "parte": numero_corte
            })
            
            inicio += duracao_corte
            numero_corte += 1
            
        clip.close()
        os.remove(caminho_temporario)
        return JSONResponse(content={"status": "sucesso", "cortes": cortes_finalizados})

    except Exception as e:
        print(f"❌ Erro: {e}")
        if os.path.exists(caminho_temporario): os.remove(caminho_temporario)
        return JSONResponse(content={"status": "erro", "mensagem": str(e)}, status_code=500)
