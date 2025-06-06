# -*- coding: utf-8 -*-
import os
import subprocess
import time

from .utils import resolver_nome_arquivo_yt_dlp

def baixar_audio_youtube(url, path_destino_param="."):
    """
    Baixa o áudio de um vídeo do YouTube como MP3 usando yt-dlp.

    Args:
        url (str): A URL do vídeo do YouTube.
        path_destino_param (str): O diretório onde o áudio MP3 será salvo.

    Returns:
        tuple: (caminho_do_arquivo_mp3, ja_existia_antes_flag) ou (None, False) em caso de erro.
    """
    try:
        print(f"Baixando áudio de: {url}")
        
        final_intended_audio_path = resolver_nome_arquivo_yt_dlp(url, path_destino_param, extrair_audio=True, audio_format="mp3")
        
        resolved_filename = os.path.basename(final_intended_audio_path) if final_intended_audio_path else None
        if not resolved_filename:
            print(f"⚠️ Não foi possível obter o nome do arquivo de áudio resolvido para {url} via --get-filename.")
            return None, False

        base, ext = os.path.splitext(resolved_filename)
        # Garante que a extensão seja .mp3, mesmo que resolver_nome_arquivo_yt_dlp já faça isso.
        resolved_filename = base + ".mp3" 

        path_destino_abs = os.path.dirname(final_intended_audio_path) if final_intended_audio_path else os.path.abspath(path_destino_param)
        if not os.path.exists(path_destino_abs):
            os.makedirs(path_destino_abs, exist_ok=True)

        # Reconstroi o caminho final com a extensão .mp3 garantida
        final_intended_audio_path = os.path.join(path_destino_abs, resolved_filename)
        print(f"   Tentando salvar áudio em: {final_intended_audio_path}")

        if os.path.exists(final_intended_audio_path):
            print(f"✅ Áudio já baixado: {os.path.basename(final_intended_audio_path)}")
            print(f"   Localizado em: {final_intended_audio_path}")
            return final_intended_audio_path, True

        download_process = subprocess.run([
            "yt-dlp", "-x", "--audio-format", "mp3",
            "-o", final_intended_audio_path, "--no-warnings", url
        ], capture_output=True, text=True, check=False, encoding='utf-8')

        if download_process.returncode == 0:
            max_retries = 3
            retry_delay_segundos = 0.2
            arquivo_encontrado_ou_ja_existia = False
            for _ in range(max_retries):
                if os.path.exists(final_intended_audio_path):
                    arquivo_encontrado_ou_ja_existia = True
                    break
                time.sleep(retry_delay_segundos)

            if arquivo_encontrado_ou_ja_existia:
                print(f"✅ Áudio processado/verificado: {os.path.basename(final_intended_audio_path)}")
                return final_intended_audio_path, False # False porque foi baixado agora
            else:
                print(f"⚠️ yt-dlp retornou sucesso, mas o arquivo de áudio '{final_intended_audio_path}' não foi encontrado.")
        
        print(f"⚠️ Erro ao baixar/processar áudio de {url} com yt-dlp.")
        print(f"   Código de retorno: {download_process.returncode}")
        print(f"   Saída (stdout):\n{download_process.stdout}")
        print(f"   Saída (stderr):\n{download_process.stderr}")
        return None, False

    except Exception as e: # Captura genérica para outros erros inesperados
        print(f"⚠️ Erro inesperado ao tentar baixar áudio de {url}: {e}")
        return None, False

def baixar_video(url, path_destino_param="."):
    """
    Baixa um vídeo usando yt-dlp.

    Args:
        url (str): The YouTube URL.
        path_destino_param (str): The directory where the video will be saved.
    Returns:
        tuple: (caminho_do_arquivo_baixado, ja_existia_antes_flag) ou (None, False) em caso de erro.
    """
    try:
        print(f"Baixando: {url}")

        final_intended_path = resolver_nome_arquivo_yt_dlp(url, path_destino_param, extrair_audio=False)

        if not final_intended_path:
             print(f"⚠️ Não foi possível resolver o nome do arquivo para {url}. Download pulado.")
             return None, False

        path_destino_abs = os.path.dirname(final_intended_path)
        if not os.path.exists(path_destino_abs):
            try:
                os.makedirs(path_destino_abs, exist_ok=True)
            except OSError as e:
                print(f"⚠️ Erro ao criar pasta de destino {path_destino_abs}: {e}")
                return None, False

        print(f"   Tentando salvar em: {final_intended_path}")

        if os.path.exists(final_intended_path):
            print(f"✅ Vídeo já baixado: {os.path.basename(final_intended_path)}")
            print(f"   Localizado em: {final_intended_path}")
            return final_intended_path, True

        download_process = subprocess.run([
            "yt-dlp", "-f", "bestvideo+bestaudio/best", "-o", final_intended_path,
            "--no-warnings", url
        ], capture_output=True, text=True, check=False, encoding='utf-8')

        if download_process.returncode == 0:
            # Adiciona uma pequena espera para o sistema de arquivos atualizar
            time.sleep(0.5) 
            if os.path.exists(final_intended_path):
                print(f"✅ Download/Verificação concluído: {os.path.basename(final_intended_path)}")
                return final_intended_path, False # False porque foi baixado agora
            else:
                print(f"⚠️ Download parece ter sido bem-sucedido (código 0), mas o arquivo '{final_intended_path}' não foi encontrado.")
        
        print(f"⚠️ Erro ao baixar/processar {url} com yt-dlp.")
        print(f"   Código de retorno: {download_process.returncode}")
        print(f"   Saída yt-dlp (stdout):\n{download_process.stdout}")
        print(f"   Saída yt-dlp (stderr):\n{download_process.stderr}")
        return None, False

    except FileNotFoundError:
        print("⚠️ Erro: yt-dlp não encontrado. Verifique se está instalado e no PATH do sistema.")
        return None, False
    except Exception as e:
        print(f"⚠️ Erro inesperado ao tentar baixar {url}: {e}")
        return None, False