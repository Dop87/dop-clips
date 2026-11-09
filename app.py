# --- TRUQUE PARA CORRIGIR O ERRO DO PILLOW / ANTIALIAS ---
import PIL.Image
from PIL import ImageDraw, ImageFont
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS
# ---------------------------------------------------------

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import yt_dlp
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
import os
import math
import random
import shutil

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PASTA_CORTES = "cortes_gerados"
os.makedirs(PASTA_CORTES, exist_ok=True)
app.mount("/cortes", StaticFiles(directory=PASTA_CORTES), name="cortes")

@app.get("/")
async def ler_index():
    return FileResponse("index.html")

def limpar_pasta_cortes():
    for arquivo in os.listdir(PASTA_CORTES):
        caminho = os.path.join(PASTA_CORTES, arquivo)
        try:
            if os.path.isfile(caminho):
                os.remove(caminho)
        except Exception as e:
            print(f"Erro ao deletar {caminho}: {e}")

@app.post("/limpar-servidor")
async def limpar_servidor():
    limpar_pasta_cortes()
    return {"mensagem": "Servidor limpo com sucesso!"}

def criar_imagem_texto(texto, largura, altura, indice):
    img = PIL.Image.new('RGBA', (largura, altura), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    tamanho_fonte = int(altura * 0.045)
    try:
        font = ImageFont.truetype("arialbd.ttf", tamanho_fonte)
    except:
        try:
            font = ImageFont.truetype("arial.ttf", tamanho_fonte)
        except:
            font = ImageFont.load_default()
            
    outline_color = (0, 0, 0, 255)
    text_color = (255, 255, 255, 255)
    y_pos = int(altura * 0.70)
    
    try:
        bbox = draw.multiline_textbbox((0, 0), texto, font=font, align="center")
        w = bbox[2] - bbox[0]
        x_pos = (largura - w) / 2
        draw.multiline_text((x_pos, y_pos), texto, font=font, fill=text_color, align="center", stroke_width=4, stroke_fill=outline_color)
    except:
        try:
            w, h = draw.textsize(texto, font=font)
            x_pos = (largura - w) / 2
            for adj in [(2,2), (-2,-2), (2,-2), (-2,2), (0,3), (3,0), (0,-3), (-3,0)]:
                draw.multiline_text((x_pos+adj[0], y_pos+adj[1]), texto, font=font, fill=outline_color, align="center")
            draw.multiline_text((x_pos, y_pos), texto, font=font, fill=text_color, align="center")
        except:
            pass
            
    caminho = f"temp_texto_{indice}.png"
    img.save(caminho)
    return caminho

@app.post("/gerar-cortes")
async def gerar_cortes(dados: dict):
    limpar_pasta_cortes()

    url = dados.get("url")
    formato_escolhido = dados.get("formato", "original")
    tempo_corte = int(dados.get("tempo", 60))
    texto_personalizado = dados.get("textoCustomizado", "")
    usar_numeracao = dados.get("autoNumeracao", False)
    
    if not url:
        return {"erro": "Nenhum link fornecido"}
    
    try:
        print(f"1. Baixando vídeo: {url}")
        
        # Cria uma cópia descartável do crachá para o yt-dlp não estragar o original
        cookie_usado = "cookies_temp.txt"
        if os.path.exists("cookies.txt"):
            shutil.copyfile("cookies.txt", cookie_usado)
        
        # --- CONFIGURAÇÃO BLINDADA COM NODEJS ATIVADO ---
        ydl_opts = {
            'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
            'merge_output_format': 'mp4',
            'outtmpl': 'video_original.%(ext)s',
            'cookiefile': cookie_usado,
            'js_runtimes': {'node': {}},
        }
        # ------------------------------------------------
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            nome_arquivo = ydl.prepare_filename(info)
            if not os.path.exists(nome_arquivo):
                nome_arquivo = "video_original.mp4"
        
        print(f"2. Iniciando os cortes de {tempo_corte} segundos...")
        video = VideoFileClip(nome_arquivo)
        duracao_total = video.duration
        
        quantidade_cortes = math.ceil(duracao_total / tempo_corte)
        arquivos_gerados = []
        
        for i in range(quantidade_cortes):
            tempo_inicio = i * tempo_corte
            tempo_fim = min((i + 1) * tempo_corte, duracao_total)
            
            if tempo_fim - tempo_inicio < 5:
                continue
                
            print(f"Cortando parte {i+1}... ({tempo_inicio}s até {tempo_fim}s)")
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
            
            texto_exibir = ""
            if usar_numeracao:
                if i == quantidade_cortes - 1:
                    texto_exibir = "FINAL"
                else:
                    texto_exibir = f"Parte {i+1}"
                    
            if texto_personalizado:
                if texto_exibir:
                    texto_exibir = f"{texto_personalizado}\n{texto_exibir}"
                else:
                    texto_exibir = texto_personalizado

            caminho_img_txt = None
            if texto_exibir:
                caminho_img_txt = criar_imagem_texto(texto_exibir, w_par, h_par, i)
                txt_clip = ImageClip(caminho_img_txt).set_duration(clip_final.duration)
                audio_original = clip_final.audio
                clip_final = CompositeVideoClip([clip_final, txt_clip])
                clip_final = clip_final.set_audio(audio_original)
            
            nome_base = f"corte_{i+1}.mp4"
            nome_saida = f"{PASTA_CORTES}/{nome_base}"
            
            clip_final.write_videofile(
                nome_saida, 
                codec="libx264", 
                audio_codec="aac", 
                logger=None,
                ffmpeg_params=["-pix_fmt", "yuv420p"]
            )
            
            if caminho_img_txt and os.path.exists(caminho_img_txt):
                os.remove(caminho_img_txt)
            
            score_viral = random.randint(65, 99)
            
            arquivos_gerados.append({
                "url": f"/cortes/{nome_base}",
                "score": score_viral
            })
            
        print("3. Processamento concluído!")
        video.close()
        if os.path.exists(nome_arquivo):
            os.remove(nome_arquivo)
        if os.path.exists(cookie_usado):
            os.remove(cookie_usado)
        
        return {"mensagem": "Sucesso", "videos": arquivos_gerados}
        
    except Exception as e:
        print(f"ERRO ENCONTRADO: {e}")
        return {"erro": str(e)}

if __name__ == "__main__":
    import uvicorn
    porta = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=porta, reload=True)