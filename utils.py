# -*- coding: utf-8 -*-
import os
import subprocess
import time

def format_seconds_to_hhmmssff(seconds, fps=25):
    """
    Converte segundos para o formato HH:MM:SS:FF.
    Args:
        seconds (float): Tempo em segundos.
        fps (int): Taxa de quadros por segundo para calcular o componente FF.
    Returns:
        str: String formatada como HH:MM:SS:FF.
    """
    if not isinstance(fps, int) or fps <= 0:
        fps = 25 # Fallback para FPS padrão

    total_frames = round(seconds * fps)
    ff = total_frames % fps
    total_seconds_int = total_frames // fps

    ss = total_seconds_int % 60
    total_minutes = total_seconds_int // 60
    mm = total_minutes % 60
    hh = total_minutes // 60

    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"

def resolver_nome_arquivo_yt_dlp(url, path_destino_param, extrair_audio=False, audio_format="mp3"):
    """
    Resolve o nome do arquivo que yt-dlp usaria, sem baixá-lo.
    Retorna o caminho completo esperado para o arquivo no diretório de destino.
    """
    try:
        cmd_get_filename = [
            "yt-dlp",
            "--get-filename",
            "--no-warnings",
            "-o", "%(title)s.%(ext)s", # Template para o nome do arquivo base
            url
        ]

        process = subprocess.run(cmd_get_filename, capture_output=True, text=True, check=True, encoding='utf-8')

        resolved_filename_lines = process.stdout.strip().split('\n')
        base_filename_from_yt_dlp = resolved_filename_lines[-1] if resolved_filename_lines else None

        if not base_filename_from_yt_dlp:
            print(f"⚠️ Não foi possível obter o nome do arquivo base para {url} via --get-filename.")
            print(f"   Saída yt-dlp (stdout):\n{process.stdout}")
            print(f"   Saída yt-dlp (stderr):\n{process.stderr}")
            return None

        if extrair_audio:
            base, _ = os.path.splitext(base_filename_from_yt_dlp)
            final_filename = base + "." + audio_format
        else:
            final_filename = base_filename_from_yt_dlp

        path_destino_abs = os.path.abspath(path_destino_param)
        final_expected_path = os.path.join(path_destino_abs, final_filename)
        return final_expected_path

    except subprocess.CalledProcessError as e:
        print(f"⚠️ Erro ao tentar obter o nome do arquivo com yt-dlp para {url}: {e.stderr.strip() if e.stderr else 'Erro desconhecido'}")
        return None
    except Exception as e: # Captura FileNotFoundError e outros
        print(f"⚠️ Erro inesperado ao resolver nome do arquivo para {url}: {e}")
        return None