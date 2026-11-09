# --- TRUQUE PARA CORRIGIR O ERRO DO PILLOW / ANTIALIAS ---
import PIL.Image
from PIL import ImageDraw, ImageFont
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS
# ---------------------------------------------------------

from fastapi import FastAPI, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import yt_dlp
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
import os
import math
import random
import shutil
import uuid
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PASTA_BASE_CORTES = "cortes_gerados"
os.makedirs(PASTA_BASE_CORTES, exist_ok=True)
app.mount("/cortes", StaticFiles(directory=PASTA_BASE_CORTES), name="cortes")

@app.get("/")
async def ler_index():
    return FileResponse("index.html")

# Limpa pastas antigas com mais de 2 horas para economizar espaço na nuvem
def limpar_pastas_antigas():
    agora = time.time()
    if os.path.exists(PASTA_BASE_CORTES):
        for pasta_usuario in os.listdir(PASTA_BASE_CORTES):
            caminho_pasta = os.path.join(PASTA_BASE_CORTES, pasta_usuario)
            if os.path.isdir(caminho_pasta):
                # Se a pasta tem mais de 2 horas, apaga
                if agora - os.path.getmtime(caminho_pasta) > 7200:
                    try:
                        shutil.rmtree(caminho_pasta)
                    except:
                        pass

@app.post("/limpar-servidor")
def limpar_servidor(client_id: str = Header(default="padrao")):
    limpar_pastas_antigas()
    pasta_usuario = os.path.join(PASTA_BASE_CORTES, client_id)
    if os.path.exists(pasta_usuario):
        try:
            shutil.rmtree(pasta_usuario)
        except Exception as e:
            print(f"Erro ao limpar pasta do usuário {client_id}: {e}")
    return {"mensagem": "Seu espaço no servidor foi limpo com sucesso!"}

def carregar_fonte_segura(tamanho):
    fontes = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "arialbd.ttf",
        "arial.ttf"
    ]
    for f in fontes:
        try:
            return ImageFont.truetype(f, tamanho)
        except:
            continue
    try:
        return ImageFont.load_default(size=tamanho)
    except:
        return ImageFont.load_default()

def criar_imagem_texto(texto, largura, altura, id_unico):
    img = PIL.Image.new('RGBA', (largura, altura), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    tamanho_fonte = int(altura * 0.045)
    font = carregar_fonte_segura(tamanho_fonte)
            
    outline_color = (0, 0, 0, 255)
    text_color = (255, 255, 255, 255)
    y_pos = int(altura * 0.70)
    
    try:
        bbox = draw.multiline_textbbox((0, 0), texto, font=font, align="center")
        w = bbox[2] - bbox[0]
        x_pos = (largura - w) / 2
        draw.multiline_text(
            (x_pos, y_pos), texto, font=font, fill=text_color, 
            align="center", stroke_width=4, stroke_fill=outline_color
        )
    except:
        pass
            
    caminho = f"temp_texto_{id_unico}.png"
    img.save(caminho)
    return caminho

@app.post("/gerar-cortes")
def gerar_cortes(dados: dict, client_id: str = Header(default="padrao")):
    limpar_pastas_antigas()

    url = dados.get("url")
    formato_escolhido = dados.get("formato", "original")
    tempo_corte = int(dados.get("tempo", 60))
    texto_personalizado = dados.get("textoCustomizado", "")
    usar_numeracao = dados.get("autoNumeracao", False)
    usar_legenda = dados.get("autoLegenda", False)
    usar_marca = dados.get("marcaDagua", False)
    
    if not url:
        return {"erro": "Nenhum link fornecido"}
    
    id_sessao = uuid.uuid4().hex[:8]
    pasta_usuario = os.path.join(PASTA_BASE_CORTES, client_id)
    os.makedirs(pasta_usuario, exist_ok=True)
    
    cookie_usado = f"cookies_{id_sessao}.txt"
    nome_arquivo = None
    video = None
    
    try:
        print(f"1. [{id_sessao}] Baixando vídeo para o usuário {client_id}: {url}")
        
        if os.path.exists("cookies.txt"):
            shutil.copyfile("cookies.txt", cookie_usado)
        
        ydl_opts = {
            'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
            'merge_output_format': 'mp4',
            'outtmpl': f'video_{id_sessao}.%(ext)s',
            'cookiefile': cookie_usado if os.path.exists(cookie_usado) else None,
            'js_runtimes': {'node': {}},
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            nome_arquivo = ydl.prepare_filename(info)
            if not os.path.exists(nome_arquivo):
                nome_arquivo = f"video_{id_sessao}.mp4"
        
        video = VideoFileClip(nome_arquivo)
        duracao_total = video.duration
        
        if duracao_total > 1800: # Trava de 30 minutos para proteger o servidor
            return {"erro": "Vídeo muito longo! Escolha links de até 30 minutos."}
        
        print(f"2. [{id_sessao}] Iniciando cortes de {tempo_corte}s...")
        quantidade_cortes = math.ceil(duracao_total / tempo_corte)
        arquivos_gerados = []
        
        for i in range(quantidade_cortes):
            tempo_inicio = i * tempo_corte
            tempo_fim = min((i + 1) * tempo_corte, duracao_total)
            
            if tempo_fim - tempo_inicio < 5:
                continue
                
            clip = video.subclip(tempo_inicio, tempo_fim)
            
            if formato_escolhido == "vertical":
                largura, altura = clip.size
                nova_largura = int(altura * 9 / 16)
                centro_x = largura / 2
                clip_final = clip.crop(x_center=centro_x, width=nova_largura)
            else:
                clip_final = clip
            
            w, h = clip_final.size
            w_par = w if w % 2 == 0 else w - 1
            h_par = h if h % 2 == 0 else h - 1
            if w != w_par or h != h_par:
                clip_final = clip_final.resize(newsize=(w_par, h_par))
            
            # Montagem de textos (Numeração + Texto Customizado + Marca d'água)
            textos_bloco = []
            if usar_numeracao:
                textos_bloco.append("FINAL" if i == quantidade_cortes - 1 else f"Parte {i+1}")
            if texto_personalizado:
                textos_bloco.append(texto_personalizado)
            if usar_marca:
                textos_bloco.append("DOP CLIPS")
            if usar_legenda and not texto_personalizado:
                textos_bloco.append("✨ [Legenda Automática Ativa]")

            texto_final_exibir = "\n".join(textos_bloco)

            caminho_img_txt = None
            if texto_final_exibir:
                caminho_img_txt = criar_imagem_texto(texto_final_exibir, w_par, h_par, f"{id_sessao}_{i}")
                txt_clip = ImageClip(caminho_img_txt).set_duration(clip_final.duration)
                audio_original = clip_final.audio
                clip_final = CompositeVideoClip([clip_final, txt_clip]).set_audio(audio_original)
            
            nome_base = f"corte_{id_sessao}_{i+1}.mp4"
            nome_saida = os.path.join(pasta_usuario, nome_base)
            
            clip_final.write_videofile(
                nome_saida, 
                codec="libx264", 
                audio_codec="aac", 
                logger=None,
                ffmpeg_params=["-pix_fmt", "yuv420p"]
            )
            
            clip_final.close()
            if caminho_img_txt and os.path.exists(caminho_img_txt):
                os.remove(caminho_img_txt)
            
            arquivos_gerados.append({
                "url": f"/cortes/{client_id}/{nome_base}",
                "score": random.randint(75, 99)
            })
            
        print(f"3. [{id_sessao}] Concluído com sucesso!")
        return {"mensagem": "Sucesso", "videos": arquivos_gerados}
        
    except Exception as e:
        print(f"ERRO ENCONTRADO: {e}")
        return {"erro": str(e)}
        
    finally:
        if video:
            try: video.close()
            except: pass
        if nome_arquivo and os.path.exists(nome_arquivo):
            try: os.remove(nome_arquivo)
            except: pass
        if os.path.exists(cookie_usado):
            try: os.remove(cookie_usado)
            except: pass

if __name__ == "__main__":
    import uvicorn
    porta = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=porta, reload=True)