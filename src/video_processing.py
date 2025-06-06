# -*- coding: utf-8 -*-
import os
import subprocess
import time
import cv2
import shutil
import json # Adicionado import json

from .utils import format_seconds_to_hhmmssff, resolver_nome_arquivo_yt_dlp

# Imports para detecção de cena
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector

def baixar_video(url, path_destino_param="."):
    """
    Baixa um vídeo usando yt-dlp.

    Args:
        url (str): The YouTube URL.
        path_destino_param (str): The directory where the video will be saved.
    Returns:
        tuple: (caminho_do_arquivo_baixado, ja_existia_antes_flag) ou (None, False) em caso de erro.
    """
    # Esta função será movida para src/downloading.py
    try:
        print(f"Baixando: {url}")

        # Use a utility function to resolve the final filename
        final_intended_path = resolver_nome_arquivo_yt_dlp(url, path_destino_param, extrair_audio=False)

        if not final_intended_path:
             print(f"⚠️ Não foi possível resolver o nome do arquivo para {url}. Download pulado.")
             return None, False

        path_destino_abs = os.path.dirname(final_intended_path) # Get directory from resolved path
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
            "yt-dlp",
            "-f", "bestvideo+bestaudio/best",
            "-o", final_intended_path,
            "--no-warnings",
            url
        ], capture_output=True, text=True, check=False, encoding='utf-8')

        if download_process.returncode == 0:
            max_retries = 3
            retry_delay_segundos = 0.5
            arquivo_encontrado = False
            for tentativa in range(max_retries):
                if os.path.exists(final_intended_path):
                    arquivo_encontrado = True
                    break
                print(f"   ...arquivo '{final_intended_path}' não encontrado na tentativa {tentativa + 1}/{max_retries}. Aguardando {retry_delay_segundos}s...")
                time.sleep(retry_delay_segundos)

            if arquivo_encontrado:
                print(f"✅ Download/Verificação concluído: {os.path.basename(final_intended_path)}")
                print(f"   Salvo em: {final_intended_path}")
                return final_intended_path, False
            else:
                print(f"⚠️ Download parece ter sido bem-sucedido (código 0), mas o arquivo '{final_intended_path}' não foi encontrado após {max_retries} tentativas.")
                print(f"   Saída do download yt-dlp (stdout):\n{download_process.stdout}")
                print(f"   Saída do download yt-dlp (stderr):\n{download_process.stderr}")
                return None, False
        else:
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

def extrair_frames(video_path, pasta_frames_saida, intervalo_segundos=1, qualidade_jpeg=55):
    if not os.path.exists(video_path):
        print(f"⚠️ Erro: Vídeo não encontrado em {video_path}")
        return []
    if not os.path.exists(pasta_frames_saida):
        try: os.makedirs(pasta_frames_saida)
        except OSError as e:
            print(f"⚠️ Erro ao criar pasta de frames {pasta_frames_saida}: {e}")
            return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"⚠️ Erro ao abrir o vídeo: {video_path}")
        return []
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0:
        print(f"⚠️ Erro: FPS do vídeo é 0 ou inválido. Não é possível extrair frames de {video_path}")
        cap.release()
        return []

    frames_extraidos_info, frame_count, num_frames_salvos, proximo_timestamp_para_salvar = [], 0, 0, 0.0
    video_basename = os.path.basename(video_path)
    print(f"\n🎞️  Extraindo frames de '{video_basename}' (FPS: {fps:.2f}) a cada {intervalo_segundos} segundo(s)...")

    while True:
        ret, frame = cap.read()
        if not ret: break
        timestamp_atual_segundos = frame_count / fps
        if timestamp_atual_segundos >= proximo_timestamp_para_salvar:
            timestamp_str_arquivo = f"{timestamp_atual_segundos:.2f}".replace('.', '_')
            nome_frame = f"frame_{num_frames_salvos:06d}_time_{timestamp_str_arquivo}s.jpg"
            caminho_frame = os.path.join(pasta_frames_saida, nome_frame)
            try:
                cv2.imwrite(caminho_frame, frame, [cv2.IMWRITE_JPEG_QUALITY, qualidade_jpeg])
                frames_extraidos_info.append((caminho_frame, timestamp_atual_segundos))
                num_frames_salvos += 1
                proximo_timestamp_para_salvar = num_frames_salvos * intervalo_segundos
            except Exception as e: print(f"⚠️ Erro ao salvar o frame {nome_frame}: {e}")
        frame_count += 1

    cap.release()
    if frames_extraidos_info:
        print(f"✅ Extração de frames de '{video_basename}' concluída. {len(frames_extraidos_info)} frames salvos em '{pasta_frames_saida}'.")
    elif not cap.isOpened() and fps > 0 :
        print(f"ℹ️ Nenhum frame extraído para '{video_basename}'. O vídeo pode ser mais curto que o intervalo de extração ou vazio.")
    return frames_extraidos_info

def detectar_cortes_de_cena(video_path, output_json_path, threshold=27.0):
    """
    Detecta mudanças de cena em um vídeo e salva os tempos de início e fim
    de cada cena contínua em um arquivo JSON.

    Args:
        video_path (str): Caminho para o arquivo de vídeo.
        output_json_path (str): Caminho para salvar o arquivo JSON com os resultados.
        threshold (float): Limiar para o ContentDetector. Valores mais baixos detectam
                           mais cortes (mais sensível). O padrão é 27.0.
    Returns:
        bool: True se a detecção foi bem-sucedida e o JSON foi salvo, False caso contrário.
    """
    if not os.path.exists(video_path):
        print(f"⚠️ Erro: Vídeo para detecção de cena não encontrado em {video_path}")
        return False

    try:
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        
        print(f"\n🔪 Detectando cortes de cena em: {os.path.basename(video_path)} (Threshold: {threshold})...")
        scene_manager.detect_scenes(video=video, show_progress=True)
        scene_list = scene_manager.get_scene_list()

        cenas_info = []
        if not scene_list:
            print(f"ℹ️ Nenhuma cena detectada em '{os.path.basename(video_path)}'.")
        else:
            print(f"✅ {len(scene_list)} cenas detectadas.")
            for i, scene in enumerate(scene_list):
                start_time = scene[0].get_seconds()
                end_time = scene[1].get_seconds()
                cenas_info.append({
                    "cena_numero": i + 1,
                    "inicio_segundos": start_time,
                    "fim_segundos": end_time,
                    "inicio_hhmmssff": format_seconds_to_hhmmssff(start_time, video.frame_rate),
                    "fim_hhmmssff": format_seconds_to_hhmmssff(end_time, video.frame_rate)
                })
        
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(cenas_info, f, indent=4, ensure_ascii=False)
        print(f"✅ Informações de corte de cena salvas em: {output_json_path}")
        return True
    except Exception as e:
        print(f"⚠️ Erro durante a detecção de cortes de cena: {e}")
        return False