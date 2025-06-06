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

def comment_line_in_file(file_path, line_content_to_comment):
    """
    Comenta uma linha específica em um arquivo se ela contiver o conteúdo fornecido
    e ainda não estiver comentada.
    """
    if not os.path.exists(file_path):
        print(f"⚠️ Arquivo para comentar linha não encontrado: {file_path}")
        return
    try:
        with open(file_path, "r", encoding='utf-8') as f:
            lines = f.readlines()
        modified = False
        new_lines = []
        for line in lines:
            stripped_line = line.strip()
            if line_content_to_comment in stripped_line and not stripped_line.startswith("#"):
                new_lines.append(f"# {line.lstrip()}")
                modified = True
            else:
                new_lines.append(line)
        if modified:
            with open(file_path, "w", encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"   Linha contendo '{line_content_to_comment}' comentada em '{os.path.basename(file_path)}'")
    except Exception as e:
        print(f"⚠️ Erro ao tentar comentar linha em '{file_path}': {e}")

def parse_hhmmssff_to_seconds(time_str, fps=25):
    if not isinstance(fps, int) or fps <= 0:
        fps = 25
    parts = time_str.split(':')
    if len(parts) != 4:
        if len(parts) == 3: parts.append("0")
        else: raise ValueError(f"Time string '{time_str}' formato inválido.")
    try:
        h, m, s, f = map(int, parts)
    except ValueError:
         raise ValueError(f"Componentes de tempo inválidos: '{time_str}'.")
    return (h * 3600 + m * 60 + s) + (f / fps)

def find_frame_by_number(frames_dir, target_frame_number_str):
    if not os.path.exists(frames_dir): return None
    try:
        target_frame_number = int(target_frame_number_str)
    except ValueError: return None
    search_prefix = f"frame_{target_frame_number:06d}_"
    for filename in os.listdir(frames_dir):
        if filename.startswith(search_prefix) and filename.lower().endswith(".jpg"):
            return os.path.join(frames_dir, filename)
    return None

def get_audio_duration(audio_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Erro ffprobe (duração) '{os.path.basename(audio_path)}': {e.stderr.strip()}")
    except FileNotFoundError:
        print("Erro: ffprobe não encontrado.")
    except ValueError:
        print(f"Erro conversão duração float: '{os.path.basename(audio_path)}'.")
    return None