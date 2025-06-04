# -*- coding: utf-8 -*-
import os
import subprocess
import time
import shutil

from utils import format_seconds_to_hhmmssff, resolver_nome_arquivo_yt_dlp

# Funções movidas de main.py

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
        
        # Use a utility function to resolve the final filename
        final_intended_audio_path = resolver_nome_arquivo_yt_dlp(url, path_destino_param, extrair_audio=True, audio_format="mp3")
        
        # The rest of the logic remains similar, but uses the resolved path
        resolved_filename = os.path.basename(final_intended_audio_path) if final_intended_audio_path else None
        if not resolved_filename:
            print(f"⚠️ Não foi possível obter o nome do arquivo de áudio resolvido para {url} via --get-filename.")
            return None, False

        base, ext = os.path.splitext(resolved_filename)
        resolved_filename = base + ".mp3"

        path_destino_abs = os.path.dirname(final_intended_audio_path) if final_intended_audio_path else os.path.abspath(path_destino_param) # Use resolved path dir
        if not os.path.exists(path_destino_abs):
            os.makedirs(path_destino_abs, exist_ok=True)

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
                return final_intended_audio_path, True
            else:
                print(f"⚠️ yt-dlp retornou sucesso, mas o arquivo de áudio '{final_intended_audio_path}' não foi encontrado.")
        
        print(f"⚠️ Erro ao baixar/processar áudio de {url} com yt-dlp.")
        print(f"   Código de retorno: {download_process.returncode}")
        print(f"   Saída (stdout):\n{download_process.stdout}")
        print(f"   Saída (stderr):\n{download_process.stderr}")
        return None, False

    except subprocess.CalledProcessError as e:
        print(f"⚠️ Erro ao tentar obter o nome do arquivo de áudio com yt-dlp para {url}: {e}")
        return None, False
    except Exception as e:
        print(f"⚠️ Erro inesperado ao tentar baixar áudio de {url}: {e}")
        return None, False

def analisar_batidas_audio(caminho_audio, pasta_saida_batidas, fps_para_timestamp=25):
    try:
        import librosa
        import numpy as np
    except ImportError:
        print("⚠️ A biblioteca 'librosa' ou 'numpy' não está instalada. Não é possível analisar batidas.")
        print("   Por favor, instale com: pip install librosa numpy")
        return None, None

    try:
        print(f"🥁 Analisando batidas para: {os.path.basename(caminho_audio)}")
        y, sr = librosa.load(caminho_audio)
        onset_envelope = librosa.onset.onset_strength(y=y, sr=sr)
        onset_frames = librosa.onset.onset_detect(onset_envelope=onset_envelope, sr=sr, units='frames')
        valid_onset_frames = [f for f in onset_frames if 0 <= f < len(onset_envelope)]
        onset_amplitudes = onset_envelope[valid_onset_frames]
        onset_times = librosa.frames_to_time(valid_onset_frames, sr=sr)

        if not onset_times.size > 0:
            print(f"ℹ️ Nenhuma batida/onset marcante detectado em '{os.path.basename(caminho_audio)}'.")
            if os.path.exists(pasta_saida_batidas):
                 try: shutil.rmtree(pasta_saida_batidas)
                 except Exception as e: print(f'⚠️ Falha ao deletar pasta {pasta_saida_batidas}. Razão: {e}')
            return None, None

        if not os.path.exists(pasta_saida_batidas):
            os.makedirs(pasta_saida_batidas, exist_ok=True)
        else:
            for filename in os.listdir(pasta_saida_batidas):
                file_path = os.path.join(pasta_saida_batidas, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path): os.unlink(file_path)
                    elif os.path.isdir(file_path): shutil.rmtree(file_path)
                except Exception as e: print(f'⚠️ Falha ao deletar {file_path}. Razão: {e}')

        beat_data = []
        for t, amp in zip(onset_times, onset_amplitudes):
            if t >= 0:
                beat_data.append({'timestamp_hhmmssff': format_seconds_to_hhmmssff(t, fps_para_timestamp), 'amplitude': float(amp)})

        if not beat_data:
             print(f"ℹ️ Nenhuma batida válida detectada. Nenhum arquivo de batidas será gerado.")
             return None, None

        arquivo_beats_with_amplitude = os.path.join(pasta_saida_batidas, "beats_with_amplitude.txt")
        with open(arquivo_beats_with_amplitude, "w", encoding='utf-8') as f_amp:
            for item in beat_data:
                f_amp.write(f"{item['timestamp_hhmmssff']},{item['amplitude']:.6f}\n")

        arquivo_saida_batidas = os.path.join(pasta_saida_batidas, "beats.txt")
        with open(arquivo_saida_batidas, "w", encoding='utf-8') as f_beats:
             for item in beat_data:
                 f_beats.write(f"{item['timestamp_hhmmssff']}\n")

        print(f"✅ Dados de batidas ({len(beat_data)} eventos) salvos.")
        return arquivo_saida_batidas, arquivo_beats_with_amplitude
    except Exception as e:
        print(f"⚠️ Erro ao analisar batidas: {e}")
        return None, None

def load_amplitude_data(amplitude_file_path):
    amplitude_map = {}
    all_amplitudes = []
    if not os.path.exists(amplitude_file_path):
        return amplitude_map, 0.0
    with open(amplitude_file_path, 'r', encoding='utf-8') as f:
        for linha in f:
            linha = linha.strip()
            if not linha: continue
            try:
                timestamp, amp_str = linha.split(',')
                amplitude = float(amp_str)
                amplitude_map[timestamp] = amplitude
                all_amplitudes.append(amplitude)
            except ValueError: continue
    return amplitude_map, (max(all_amplitudes) if all_amplitudes else 0.0)

def filter_timestamps_by_amplitude(timestamps_file_path, amplitude_map, overall_max_amplitude, min_amplitude_percentage):
    if not amplitude_map or overall_max_amplitude == 0:
        print("Aviso: Mapa de amplitudes vazio ou amp máxima zero. Sem filtragem.")
        return False
    if not os.path.exists(timestamps_file_path):
        print(f"Erro: Arquivo de timestamps '{timestamps_file_path}' não encontrado.")
        return False

    limite_inferior = (min_amplitude_percentage / 100.0) * overall_max_amplitude
    filtered_timestamps, original_count = [], 0

    with open(timestamps_file_path, 'r', encoding='utf-8') as f:
        for linha in f:
            timestamp = linha.strip()
            if not timestamp: continue
            original_count += 1
            beat_amp = amplitude_map.get(timestamp)
            if beat_amp is not None and beat_amp >= limite_inferior:
                filtered_timestamps.append(timestamp)
    try:
        with open(timestamps_file_path, 'w', encoding='utf-8') as f:
            for ts in filtered_timestamps: f.write(f"{ts}\n")
        print(f"✅ Filtragem por amplitude: {os.path.basename(timestamps_file_path)} (Original: {original_count}, Filtrado: {len(filtered_timestamps)})")
        return True
    except Exception as e:
        print(f"⚠️ Erro ao salvar timestamps filtrados: {e}")
        return False