import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont
import numpy as np
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, clips_array, concatenate_videoclips
import whisper
import cv2
import shutil
import os
import random
import uuid
from typing import Optional, List

app = FastAPI()
PASTA_CORTES = "cortes_gerados"
os.makedirs(PASTA_CORTES, exist_ok=True)
app.mount("/cortes_gerados", StaticFiles(directory=PASTA_CORTES), name="cortes")

# Carrega a IA de Legendas (Modelo 'tiny' para economia de RAM)
print("Carregando IA Whisper (Legendas)...")
modelo_whisper = whisper.load_model("tiny")
print("Motor de IA Pronto!")

@app.get("/")
async def home():
    return FileResponse("index.html")

# --- FUNÇÕES DE INTELIGÊNCIA E MATEMÁTICA ---

def criar_imagem_texto(texto, largura=1080, altura=200, cor="white", borda="black"):
    img = PIL.Image.new('RGBA', (largura, altura), (255, 255, 255, 0))
    d = PIL.ImageDraw.Draw(img)
    try: font = PIL.ImageFont.truetype("arial.ttf", 65)
    except IOError: font = PIL.ImageFont.load_default()
    
    text_w, text_h = d.textsize(texto, font=font) if hasattr(d, 'textsize') else (400, 80)
    x, y = (largura - text_w) / 2, (altura - text_h) / 2
    
    # Borda grossa para legibilidade no TikTok
    borda_size = 4
    for ox in [-borda_size, 0, borda_size]:
        for oy in [-borda_size, 0, borda_size]: d.text((x + ox, y + oy), texto, fill=borda, font=font)
    d.text((x, y), texto, fill=cor, font=font)
    return np.array(img)

def ia_auto_framing(clip):
    """Detecta o rosto central e corta em formato Vertical 9:16 seguindo o rosto"""
    frame = clip.get_frame(clip.duration / 2) 
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    caminho_cascade = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(caminho_cascade)
    rostos = face_cascade.detectMultiScale(gray, 1.3, 5)
    
    (w, h) = clip.size
    nova_largura = h * (9/16)
    centro_x = w / 2 
    
    if len(rostos) > 0:
        (x, y, fw, fh) = rostos[0]
        centro_x = x + (fw / 2)
        print("🤖 Rosto rastreado para o formato IA!")
        
    x1, x2 = max(0, centro_x - (nova_largura / 2)), min(w, centro_x + (nova_largura / 2))
    if x1 == 0: x2 = nova_largura
    if x2 == w: x1 = w - nova_largura
    
    return clip.crop(x1=x1, y1=0, x2=x2, y2=h).resize(height=1920, width=1080)

def redimensionar_e_cortar(clip, target_w=1080, target_h=960):
    """Preenche perfeitamente um bloco 1080x960 sem achatar a imagem"""
    ratio_clip = clip.w / clip.h
    ratio_target = target_w / target_h
    if ratio_clip > ratio_target: clip_resized = clip.resize(height=target_h)
    else: clip_resized = clip.resize(width=target_w)
    return clip_resized.crop(x_center=clip_resized.w/2, y_center=clip_resized.h/2, width=target_w, height=target_h)

# --- ROTA PRINCIPAL DE PROCESSAMENTO ---

@app.post("/processar-video")
async def processar_video(
    video: UploadFile = File(...),
    fundo_videos: Optional[List[UploadFile]] = File(None),
    duracao_corte: int = Form(60),
    formato: str = Form("original"),
    tipo_texto: str = Form("nenhum"),
    texto_usuario: str = Form(""),
    legendas: Optional[str] = Form(None),
    tela_dividida: Optional[str] = Form(None)
):
    print(f"📥 Recebendo vídeo principal: {video.filename}")
    usar_legendas = (legendas == "on")
    usar_tela_dividida = (tela_dividida == "on")
    
    # 1. Salva Vídeo Principal
    cam_principal = f"temp_{uuid.uuid4().hex}.mp4"
    with open(cam_principal, "wb") as buffer: shutil.copyfileobj(video.file, buffer)
    
    # 2. Salva e Combina Vídeos de Fundo (Se a Tela Dividida estiver ativa)
    fundo_master_clip = None
    arquivos_fundo_temp = []
    if usar_tela_dividida and fundo_videos and len(fundo_videos) > 0 and fundo_videos[0].filename != "":
        print(f"🎮 Carregando {len(fundo_videos)} vídeos de fundo...")
        clips_fundo = []
        for fv in fundo_videos:
            cam_fundo = f"temp_bg_{uuid.uuid4().hex}.mp4"
            with open(cam_fundo, "wb") as buffer: shutil.copyfileobj(fv.file, buffer)
            arquivos_fundo_temp.append(cam_fundo)
            clips_fundo.append(VideoFileClip(cam_fundo))
        fundo_master_clip = concatenate_videoclips(clips_fundo) # Une todos num vídeo gigante
        
    cortes_finalizados = []
    
    try:
        clip = VideoFileClip(cam_principal)
        inicio, numero_corte = 0, 1
        
        while inicio < clip.duration:
            fim = min(inicio + duracao_corte, clip.duration)
            if (fim - inicio) < 5: break # Ignora rebarba menor que 5s
                
            trecho = clip.subclip(inicio, fim)
            (w_orig, h_orig) = trecho.size
            camadas = []
            
            # --- TELA DIVIDIDA MULTI-VÍDEO (50/50) ---
            if usar_tela_dividida and fundo_master_clip is not None:
                # Topo (Vídeo Principal)
                trecho_cima = redimensionar_e_cortar(trecho, 1080, 960)
                
                # Fundo (Rodízio em loop)
                inicio_fundo = inicio % fundo_master_clip.duration
                fim_fundo = min(inicio_fundo + trecho.duration, fundo_master_clip.duration)
                fundo_trecho = fundo_master_clip.subclip(inicio_fundo, fim_fundo)
                
                # Se faltar tempo no fundo, faz um loop imediato
                if fundo_trecho.duration < trecho.duration:
                    fundo_trecho = fundo_trecho.loop(duration=trecho.duration)
                
                fundo_baixo = redimensionar_e_cortar(fundo_trecho.without_audio(), 1080, 960)
                trecho = clips_array([[trecho_cima], [fundo_baixo]])
                
            # --- FORMATOS NORMAIS ---
            else:
                if formato == "vertical_bordas":
                    trecho = trecho.resize(width=1080).margin(top=400, bottom=400, color=(0,0,0))
                elif formato == "corte_central":
                    trecho = trecho.crop(x1=w_orig/2 - h_orig*(9/32), y1=0, x2=w_orig/2 + h_orig*(9/32), y2=h_orig).resize(height=1920, width=1080)
                elif formato == "premium_ia":
                    trecho = ia_auto_framing(trecho)
            
            camadas.append(trecho)
            (w_atual, h_atual) = trecho.size

            # --- TEXTOS FIXOS / SEQUENCIAIS ---
            texto_final = ""
            if tipo_texto == "fixo" and texto_usuario: texto_final = texto_usuario
            elif tipo_texto == "sequencial" and texto_usuario: texto_final = f"{texto_usuario} {numero_corte}"
            
            if texto_final:
                img_texto = criar_imagem_texto(texto_final, largura=w_atual, altura=200)
                pos_y = 100 if not usar_tela_dividida else 50 # Sobe o texto se a tela for dividida
                camadas.append(ImageClip(img_texto).set_duration(trecho.duration).set_position(('center', pos_y)))

            # --- LEGENDAS ANIMADAS (IA Whisper) ---
            if usar_legendas:
                print(f"🎙️ Gerando Legendas do Corte {numero_corte}...")
                audio_tmp = f"audio_{uuid.uuid4().hex}.wav"
                trecho.audio.write_audiofile(audio_tmp, logger=None)
                resultado_ia = modelo_whisper.transcribe(audio_tmp, language="pt")
                
                for segmento in resultado_ia['segments']:
                    txt_legenda = criar_imagem_texto(segmento['text'].strip(), largura=w_atual, altura=300, cor="yellow")
                    # Se for tela dividida, a legenda fica no meio exato da divisão
                    pos_y_leg = 'center' if not usar_tela_dividida else 810 
                    clip_legenda = ImageClip(txt_legenda).set_start(segmento['start']).set_end(segmento['end']).set_position(('center', pos_y_leg))
                    camadas.append(clip_legenda)
                os.remove(audio_tmp)

            # --- RENDERIZA FINAL ---
            trecho_final = CompositeVideoClip(camadas) if len(camadas) > 1 else camadas[0]
            nome_arquivo = f"corte_{numero_corte}_{uuid.uuid4().hex[:4]}.mp4"
            caminho_saida = os.path.join(PASTA_CORTES, nome_arquivo)
            
            print(f"⚙️ Renderizando corte {numero_corte}...")
            trecho_final.write_videofile(
                caminho_saida, codec="libx264", audio_codec="aac", 
                fps=24, preset="ultrafast", threads=1, logger=None
            )
            trecho_final.close()
            
            cortes_finalizados.append({"url": f"/cortes_gerados/{nome_arquivo}", "score": random.randint(75, 99), "parte": numero_corte})
            
            inicio += duracao_corte
            numero_corte += 1
            
        # Limpeza de Memória
        clip.close()
        os.remove(cam_principal)
        if fundo_master_clip: fundo_master_clip.close()
        for cam in arquivos_fundo_temp: os.remove(cam)
            
        return JSONResponse(content={"status": "sucesso", "cortes": cortes_finalizados})

    except Exception as e:
        print(f"❌ Erro fatal: {e}")
        return JSONResponse(content={"status": "erro", "mensagem": str(e)}, status_code=500)
