import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont
import numpy as np
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, clips_array, concatenate_videoclips
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

def criar_imagem_texto(texto, largura=1080, altura=200, cor="white", borda="black"):
    img = PIL.Image.new('RGBA', (largura, altura), (255, 255, 255, 0))
    d = PIL.ImageDraw.Draw(img)
    try: font = PIL.ImageFont.truetype("arial.ttf", 65)
    except IOError: font = PIL.ImageFont.load_default()
    
    text_w, text_h = d.textsize(texto, font=font) if hasattr(d, 'textsize') else (400, 80)
    x, y = (largura - text_w) / 2, (altura - text_h) / 2
    
    borda_size = 4
    for ox in [-borda_size, 0, borda_size]:
        for oy in [-borda_size, 0, borda_size]: d.text((x + ox, y + oy), texto, fill=borda, font=font)
    d.text((x, y), texto, fill=cor, font=font)
    return np.array(img)

def redimensionar_e_cortar(clip, target_w=1080, target_h=960):
    ratio_clip = clip.w / clip.h
    ratio_target = target_w / target_h
    if ratio_clip > ratio_target: clip_resized = clip.resize(height=target_h)
    else: clip_resized = clip.resize(width=target_w)
    return clip_resized.crop(x_center=clip_resized.w/2, y_center=clip_resized.h/2, width=target_w, height=target_h)

@app.post("/processar-video")
async def processar_video(request: Request):
    form = await request.form()
    
    video = form.get("video")
    duracao_corte = int(form.get("duracao_corte", 60))
    formato = form.get("formato", "original")
    tipo_texto = form.get("tipo_texto", "nenhum")
    texto_usuario = form.get("texto_usuario", "")
    tela_dividida = form.get("tela_dividida")
    
    fundo_videos_raw = form.getlist("fundo_videos")
    fundo_videos = [f for f in fundo_videos_raw if hasattr(f, "filename") and f.filename != ""]

    if not video or not hasattr(video, "filename") or video.filename == "":
        return JSONResponse(content={"status": "erro", "mensagem": "Nenhum vídeo principal recebido."}, status_code=400)

    print(f"📥 Recebendo vídeo: {video.filename}")
    usar_tela_dividida = (tela_dividida == "on")
    
    cam_principal = f"temp_{uuid.uuid4().hex}.mp4"
    with open(cam_principal, "wb") as buffer: 
        shutil.copyfileobj(video.file, buffer)
    
    fundo_master_clip = None
    arquivos_fundo_temp = []
    clip = None
    
    try:
        if usar_tela_dividida and len(fundo_videos) > 0:
            print(f"🎮 Carregando {len(fundo_videos)} vídeos de fundo...")
            clips_fundo = []
            for fv in fundo_videos:
                cam_fundo = f"temp_bg_{uuid.uuid4().hex}.mp4"
                with open(cam_fundo, "wb") as buffer: 
                    shutil.copyfileobj(fv.file, buffer)
                arquivos_fundo_temp.append(cam_fundo)
                clips_fundo.append(VideoFileClip(cam_fundo))
                
            fundo_master_clip = concatenate_videoclips(clips_fundo, method="compose")
            
        cortes_finalizados = []
        clip = VideoFileClip(cam_principal)
        inicio, numero_corte = 0, 1
        
        while inicio < clip.duration:
            fim = min(inicio + duracao_corte, clip.duration)
            if (fim - inicio) < 5: break 
                
            trecho = clip.subclip(inicio, fim)
            (w_orig, h_orig) = trecho.size
            camadas = []
            
            # --- TELA DIVIDIDA 50/50 COM MÚLTIPLOS FUNDOS ---
            if usar_tela_dividida and fundo_master_clip is not None:
                trecho_cima = redimensionar_e_cortar(trecho, 1080, 960)
                inicio_fundo = inicio % fundo_master_clip.duration
                fim_fundo = min(inicio_fundo + trecho.duration, fundo_master_clip.duration)
                fundo_trecho = fundo_master_clip.subclip(inicio_fundo, fim_fundo)
                
                if fundo_trecho.duration < trecho.duration:
                    fundo_trecho = fundo_trecho.loop(duration=trecho.duration)
                
                fundo_baixo = redimensionar_e_cortar(fundo_trecho.without_audio(), 1080, 960)
                trecho = clips_array([[trecho_cima], [fundo_baixo]])
            else:
                if formato == "vertical_bordas":
                    trecho = trecho.resize(width=1080).margin(top=400, bottom=400, color=(0,0,0))
                elif formato == "corte_central":
                    trecho = trecho.crop(x1=w_orig/2 - h_orig*(9/32), y1=0, x2=w_orig/2 + h_orig*(9/32), y2=h_orig).resize(height=1920, width=1080)
                elif formato == "premium_ia":
                    trecho = trecho.resize(width=1080).margin(top=400, bottom=400, color=(0,0,0))
            
            camadas.append(trecho)
            (w_atual, h_atual) = trecho.size

            # --- TEXTOS FIXOS / SEQUENCIAIS ---
            texto_final = ""
            if tipo_texto == "fixo" and texto_usuario: texto_final = texto_usuario
            elif tipo_texto == "sequencial" and texto_usuario: texto_final = f"{texto_usuario} {numero_corte}"
            
            if texto_final:
                img_texto = criar_imagem_texto(texto_final, largura=w_atual, altura=200)
                pos_y = 100 if not usar_tela_dividida else 50 
                camadas.append(ImageClip(img_texto).set_duration(trecho.duration).set_position(('center', pos_y)))

            trecho_final = CompositeVideoClip(camadas) if len(camadas) > 1 else camadas[0]
            nome_arquivo = f"corte_{numero_corte}_{uuid.uuid4().hex[:4]}.mp4"
            caminho_saida = os.path.join(PASTA_CORTES, nome_arquivo)
            
            print(f"⚙️ Renderizando corte {numero_corte}...")
            trecho_final.write_videofile(
                caminho_saida, codec="libx264", audio_codec="aac", 
                fps=24, preset="ultrafast", threads=1, logger=None
            )
            
            # O COMANDO QUE CAUSAVA O ERRO DE TRAVAMENTO ESTAVA AQUI E FOI REMOVIDO!
            
            cortes_finalizados.append({"url": f"/cortes_gerados/{nome_arquivo}", "score": random.randint(75, 99), "parte": numero_corte})
            
            inicio += duracao_corte
            numero_corte += 1
            
        return JSONResponse(content={"status": "sucesso", "cortes": cortes_finalizados})

    except Exception as e:
        print(f"❌ Erro fatal no processamento: {e}")
        return JSONResponse(content={"status": "erro", "mensagem": f"Falha interna: {str(e)}"}, status_code=500)
        
    finally:
        # SISTEMA DE LIMPEZA BLINDADO: Só fecha os originais DEPOIS que todos os cortes terminarem
        try:
            if clip: clip.close()
        except: pass
        try:
            if fundo_master_clip: fundo_master_clip.close()
        except: pass
        
        if os.path.exists(cam_principal): os.remove(cam_principal)
        for cam in arquivos_fundo_temp: 
            if os.path.exists(cam): os.remove(cam)
