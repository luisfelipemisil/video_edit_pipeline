import os
import subprocess
import time
import cv2
from dotenv import load_dotenv
import json
import shutil
import random
import platform
import sys # Importar sys para verificar se librosa está disponível

# --- Funções de Suporte para Análise de Batidas e Filtragem ---

def load_amplitude_data(amplitude_file_path):
    """
    Carrega todos os pares timestamp-amplitude de um arquivo de referência
    e determina a maior amplitude.
    Formato esperado por linha: HH:MM:SS:FF,amplitude
    Retorna um dicionário mapeando timestamps para amplitudes e a max_amplitude.
    """
    amplitude_map = {}
    all_amplitudes = []

    if not os.path.exists(amplitude_file_path):
        # print(f"Erro: Arquivo de referência de amplitudes '{amplitude_file_path}' não encontrado.") # Suppress error here, handled by caller
        return amplitude_map, 0.0

    with open(amplitude_file_path, 'r', encoding='utf-8') as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                timestamp, amp_str = linha.split(',')
                amplitude = float(amp_str)
                amplitude_map[timestamp] = amplitude
                all_amplitudes.append(amplitude)
            except ValueError:
                # print(f"Aviso: Linha ignorada (formato inválido no arquivo de amplitudes): '{linha}'") # Suppress warning here
                continue

    max_amplitude = max(all_amplitudes) if all_amplitudes else 0.0
    return amplitude_map, max_amplitude

def filter_timestamps_by_amplitude(
    timestamps_file_path,
    amplitude_map,
    overall_max_amplitude,
    min_amplitude_percentage
):
    """
    Filtra timestamps de um arquivo especificado (contendo apenas timestamps)
    baseado em suas amplitudes (buscadas no amplitude_map) em relação à overall_max_amplitude.
    Salva os timestamps filtrados de volta no arquivo original.
    """
    if not amplitude_map or overall_max_amplitude == 0:
        print("Aviso: Mapa de amplitudes vazio ou amplitude máxima é zero. Nenhum timestamp será filtrado.")
        return False # Indicate filtering was not applied

    if not os.path.exists(timestamps_file_path):
        print(f"Erro: Arquivo de timestamps para filtrar '{timestamps_file_path}' não encontrado.")
        return False # Indicate filtering was not applied

    limite_inferior_amplitude = (min_amplitude_percentage / 100.0) * overall_max_amplitude
    filtered_timestamps = []
    original_timestamps_count = 0

    with open(timestamps_file_path, 'r', encoding='utf-8') as f:
        for linha in f:
            timestamp = linha.strip()
            if not timestamp:
                continue
            original_timestamps_count += 1

            beat_amplitude = amplitude_map.get(timestamp)

            if beat_amplitude is None:
                # print(f"Aviso: Amplitude não encontrada para o timestamp '{timestamp}'. Será ignorado.")
                continue

            if beat_amplitude >= limite_inferior_amplitude:
                filtered_timestamps.append(timestamp)

    # Overwrite the original beats file with filtered timestamps
    try:
        with open(timestamps_file_path, 'w', encoding='utf-8') as f:
            for ts in filtered_timestamps:
                f.write(f"{ts}\n")
        print(f"✅ Filtragem por amplitude concluída para '{os.path.basename(timestamps_file_path)}'.")
        print(f"   Original: {original_timestamps_count} batidas")
        print(f"   Filtrado (>= {min_amplitude_percentage}% da maior amplitude): {len(filtered_timestamps)} batidas")
        return True # Indicate filtering was applied
    except Exception as e:
        print(f"⚠️ Erro ao escrever timestamps filtrados de volta para '{timestamps_file_path}': {e}")
        return False # Indicate filtering failed


# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração da API Key da OpenAI (mantida caso você precise dela para outras coisas, mas não usada para análise)
try:
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        # print("⚠️ OPENAI_API_KEY não encontrada no ambiente.") # Comentado para reduzir logs se não for usada
        pass
except Exception as e:
    # print(f"⚠️ Erro ao carregar OPENAI_API_KEY: {e}") # Comentado para reduzir logs se não for usada
    pass

def comment_line_in_file(file_path, line_content_to_comment):
    """
    Comenta uma linha específica em um arquivo se ela contiver o conteúdo fornecido
    e ainda não estiver comentada.

    Args:
        file_path (str): O caminho para o arquivo.
        line_content_to_comment (str): O conteúdo da linha a ser comentada.
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
                new_lines.append(f"# {line.lstrip()}") # Adiciona # e mantém indentação original se houver
                modified = True
                print(f"   Comentando linha contendo '{line_content_to_comment}' em '{os.path.basename(file_path)}'")
            else:
                new_lines.append(line)

        if modified:
            with open(file_path, "w", encoding='utf-8') as f:
                f.writelines(new_lines)
    except Exception as e:
        print(f"⚠️ Erro ao tentar comentar linha em '{file_path}': {e}")

def extrair_frames(video_path, pasta_frames_saida, intervalo_segundos=1, qualidade_jpeg=55):
    """
    Extrai frames de um vídeo em intervalos regulares e retorna seus caminhos e timestamps.

    Args:
        video_path (str): Caminho para o arquivo de vídeo.
        pasta_frames_saida (str): Pasta onde os frames extraídos serão salvos.
        intervalo_segundos (float): Intervalo em segundos para extrair frames.
                                     Ex: 1 para um frame por segundo.
        qualidade_jpeg (int): Qualidade para salvar frames JPEG (0-100).
                              Padrão é 55 (conforme assinatura da função).

    Returns:
        list: Uma lista de tuplas (caminho_do_frame, timestamp_em_segundos).
              Retorna uma lista vazia se o vídeo não puder ser aberto ou ocorrer um erro.
    """
    if not os.path.exists(video_path):
        print(f"⚠️ Erro: Vídeo não encontrado em {video_path}")
        return []

    if not os.path.exists(pasta_frames_saida):
        try:
            os.makedirs(pasta_frames_saida)
            print(f"Pasta de frames criada: {pasta_frames_saida}")
        except OSError as e:
            print(f"⚠️ Erro ao criar pasta de frames {pasta_frames_saida}: {e}")
            return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"⚠️ Erro ao abrir o vídeo: {video_path}")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0: # Evita divisão por zero se o FPS não puder ser lido
        print(f"⚠️ Erro: FPS do vídeo é 0 ou inválido. Não é possível extrair frames de {video_path}")
        cap.release()
        return []

    frames_extraidos_info = []
    frame_count = 0
    num_frames_salvos = 0
    proximo_timestamp_para_salvar = 0.0

    video_basename = os.path.basename(video_path)
    print(f"\n🎞️  Extraindo frames de '{video_basename}' (FPS: {fps:.2f}) a cada {intervalo_segundos} segundo(s)...")

    while True:
        ret, frame = cap.read()
        if not ret:
            break # Fim do vídeo ou erro ao ler o frame

        timestamp_atual_segundos = frame_count / fps

        if timestamp_atual_segundos >= proximo_timestamp_para_salvar:
            # Formata o timestamp para inclusão no nome do arquivo, substituindo '.' por '_'
            timestamp_str_arquivo = f"{timestamp_atual_segundos:.2f}".replace('.', '_')
            nome_frame = f"frame_{num_frames_salvos:06d}_time_{timestamp_str_arquivo}s.jpg"
            caminho_frame = os.path.join(pasta_frames_saida, nome_frame)

            try:
                cv2.imwrite(caminho_frame, frame, [cv2.IMWRITE_JPEG_QUALITY, qualidade_jpeg])
                frames_extraidos_info.append((caminho_frame, timestamp_atual_segundos))
                num_frames_salvos += 1
                # Define o próximo ponto de salvamento.
                # Se intervalo_segundos for muito pequeno (ex: 0), isso pode levar a salvar muitos frames.
                # Garanta que intervalo_segundos seja razoável.
                proximo_timestamp_para_salvar = num_frames_salvos * intervalo_segundos
            except Exception as e:
                print(f"⚠️ Erro ao salvar o frame {nome_frame}: {e}")
                # Decide se quer continuar ou parar em caso de erro de escrita de frame
                # break # ou continue

        frame_count += 1

    cap.release()
    if frames_extraidos_info:
        print(f"✅ Extração de frames de '{video_basename}' concluída. {len(frames_extraidos_info)} frames salvos em '{pasta_frames_saida}'.")
    elif not cap.isOpened() and fps > 0 : # Se o vídeo foi aberto mas nenhum frame foi salvo (ex: vídeo muito curto)
        print(f"ℹ️ Nenhum frame extraído para '{video_basename}'. O vídeo pode ser mais curto que o intervalo de extração ou vazio.")
    return frames_extraidos_info


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

        # Etapa 1: Obter o nome do arquivo que yt-dlp usaria (sanitizado, com extensão correta)
        # Usamos um template simples aqui, pois só queremos o nome base do arquivo.
        get_filename_process = subprocess.run([
            "yt-dlp",
            "--get-filename",
            "-o", "%(title)s.%(ext)s", # Template para obter apenas o nome do arquivo
            "--no-warnings",
            url
        ], capture_output=True, text=True, check=True, encoding='utf-8') # check=True para capturar erros aqui

        resolved_filename_lines = get_filename_process.stdout.strip().split('\n')
        resolved_filename = resolved_filename_lines[-1] if resolved_filename_lines else None

        if not resolved_filename:
            print(f"⚠️ Não foi possível obter o nome do arquivo resolvido para {url} via --get-filename.")
            print(f"   Saída yt-dlp (stdout):\n{get_filename_process.stdout}")
            print(f"   Saída yt-dlp (stderr):\n{get_filename_process.stderr}")
            return None, False

        # Etapa 2: Construir o caminho de destino absoluto final e realizar o download
        path_destino_abs = os.path.abspath(path_destino_param)
        if not os.path.exists(path_destino_abs):
            try:
                os.makedirs(path_destino_abs, exist_ok=True)
            except OSError as e:
                print(f"⚠️ Erro ao criar pasta de destino {path_destino_abs}: {e}")
                return None, False

        final_intended_path = os.path.join(path_destino_abs, resolved_filename)
        print(f"   Tentando salvar em: {final_intended_path}")

        # Etapa 2.1: Verificar se o vídeo já existe no caminho final pretendido
        if os.path.exists(final_intended_path):
            print(f"✅ Vídeo já baixado: {os.path.basename(final_intended_path)}")
            print(f"   Localizado em: {final_intended_path}")
            return final_intended_path, True

        download_process = subprocess.run([
            "yt-dlp",
            "-f", "bestvideo+bestaudio/best", # Formato de alta qualidade
            "-o", final_intended_path,        # Caminho de saída absoluto e completo
            "--no-warnings",                  # Suprime avisos (opcional)
            url
        ], capture_output=True, text=True, check=False, encoding='utf-8')

        if download_process.returncode == 0:
            # Verificar a existência do arquivo no caminho que NÓS especificamos
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
                return final_intended_path, False # False porque foi baixado agora
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

    except subprocess.CalledProcessError as e: # Erro ao obter o nome do arquivo
        print(f"⚠️ Erro ao tentar obter o nome do arquivo com yt-dlp para {url}: {e}")
        print(f"   Comando: {' '.join(e.cmd)}")
        print(f"   Saída yt-dlp (stdout):\n{e.stdout}")
        print(f"   Saída yt-dlp (stderr):\n{e.stderr}")
        return None, False
    except FileNotFoundError: # yt-dlp não encontrado
        print("⚠️ Erro: yt-dlp não encontrado. Verifique se está instalado e no PATH do sistema.")
        return None, False
    except Exception as e:
        print(f"⚠️ Erro inesperado ao tentar baixar {url}: {e}")
        return None, False

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

        # Etapa 1: Obter o nome do arquivo que yt-dlp usaria para o áudio MP3
        get_filename_process = subprocess.run([
            "yt-dlp",
            "--get-filename",
            "-x", # Extrair áudio
            "--audio-format", "mp3",
            "-o", "%(title)s.%(ext)s", # Template para obter o nome do arquivo com título e extensão mp3
            "--no-warnings",
            url
        ], capture_output=True, text=True, check=True, encoding='utf-8')

        resolved_filename_lines = get_filename_process.stdout.strip().split('\n')
        resolved_filename = resolved_filename_lines[-1] if resolved_filename_lines else None

        if not resolved_filename:
            print(f"⚠️ Não foi possível obter o nome do arquivo de áudio resolvido para {url} via --get-filename.")
            return None, False

        # Garante que o nome do arquivo resolvido tenha a extensão .mp3
        base, ext = os.path.splitext(resolved_filename)
        resolved_filename = base + ".mp3"

        path_destino_abs = os.path.abspath(path_destino_param)
        if not os.path.exists(path_destino_abs):
            os.makedirs(path_destino_abs, exist_ok=True)

        final_intended_audio_path = os.path.join(path_destino_abs, resolved_filename)
        print(f"   Tentando salvar áudio em: {final_intended_audio_path}")

        if os.path.exists(final_intended_audio_path):
            print(f"✅ Áudio já baixado: {os.path.basename(final_intended_audio_path)}")
            print(f"   Localizado em: {final_intended_audio_path}")
            return final_intended_audio_path, True

        download_process = subprocess.run([
            "yt-dlp",
            "-x", # Extrair áudio
            "--audio-format", "mp3",
            "-o", final_intended_audio_path, # Caminho de saída absoluto e completo
            "--no-warnings",
            url
        ], capture_output=True, text=True, check=False, encoding='utf-8')

        if download_process.returncode == 0:
            # yt-dlp succeeded. Now, let's ensure the file exists at the intended path.
            # This handles cases where yt-dlp might have downloaded it or confirmed it already exists.
            max_retries = 3
            retry_delay_segundos = 0.2 # Shorter delay as yt-dlp has finished
            arquivo_encontrado_ou_ja_existia = False
            for _ in range(max_retries):
                if os.path.exists(final_intended_audio_path):
                    arquivo_encontrado_ou_ja_existia = True
                    break
                time.sleep(retry_delay_segundos)

            if arquivo_encontrado_ou_ja_existia:
                print(f"✅ Áudio processado/verificado: {os.path.basename(final_intended_audio_path)}")
                # We can't reliably tell from yt-dlp's output alone if it was *just* downloaded
                # or if it *already existed* without more complex parsing of stdout.
                return final_intended_audio_path, True # Assume it existed or was just successfully processed
            else:
                print(f"⚠️ yt-dlp retornou sucesso, mas o arquivo de áudio '{final_intended_audio_path}' não foi encontrado.")
        # else (erro no download_process)

        # Se chegou aqui, houve um erro ou o arquivo não foi encontrado após sucesso aparente
        print(f"⚠️ Erro ao baixar/processar áudio de {url} com yt-dlp.")
        print(f"   Código de retorno: {download_process.returncode}")
        print(f"   Saída (stdout):\n{download_process.stdout}")
        print(f"   Saída (stderr):\n{download_process.stderr}")
        return None, False

    except subprocess.CalledProcessError as e: # Erro ao obter o nome do arquivo
        print(f"⚠️ Erro ao tentar obter o nome do arquivo de áudio com yt-dlp para {url}: {e}")
        print(f"   Comando: {' '.join(e.cmd)}")
        print(f"   Saída yt-dlp (stdout):\n{e.stdout}")
        print(f"   Saída yt-dlp (stderr):\n{e.stderr}")
        return None, False

    except Exception as e:
        print(f"⚠️ Erro inesperado ao tentar baixar áudio de {url}: {e}")
        return None, False

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

def analisar_batidas_audio(caminho_audio, pasta_saida_batidas, fps_para_timestamp=25):
    """
    Analisa um arquivo de áudio para detectar batidas, calcula suas amplitudes
    e salva os timestamps (filtrados ou não) e os dados completos em arquivos .txt.

    Args:
        caminho_audio (str): Caminho para o arquivo de áudio (ex: .mp3).
        pasta_saida_batidas (str): Diretório onde o arquivo .txt com os timestamps das batidas será salvo.
                                   Serão criados 'beats.txt' (timestamps) e
                                   'beats_with_amplitude.txt' (timestamps,amplitude).
        fps_para_timestamp (int): FPS a ser usado para formatar o timestamp de saída como HH:MM:SS:FF.
    Returns:
        tuple: (Caminho para 'beats.txt', Caminho para 'beats_with_amplitude.txt') ou (None, None) em caso de falha.
    """
    try: # Importa librosa e numpy aqui para que o script principal possa rodar sem eles se a análise estiver desabilitada
        import librosa  # Biblioteca para análise de áudio
        import numpy as np # Necessário para manipulação de arrays
    except ImportError:
        print("⚠️ A biblioteca 'librosa' ou 'numpy' não está instalada. Não é possível analisar batidas.")
        print("   Por favor, instale com: pip install librosa numpy")
        return None, None

    try:
        print(f"🥁 Analisando batidas para: {os.path.basename(caminho_audio)}")

        # Carrega o arquivo de áudio. librosa.load retorna o array de áudio (y) e a taxa de amostragem (sr)
        y, sr = librosa.load(caminho_audio)

        # Calculate onset strength envelope
        # This gives a measure of "how much is happening" at each point in time,
        # often related to percussive energy.
        onset_envelope = librosa.onset.onset_strength(y=y, sr=sr)

        # Detect onsets (peaks in the onset envelope)
        # These are the moments identified as "beats" or significant percussive events.
        # Onsets are generally more suitable for capturing
        # eventos percussivos marcantes (kicks, snares, etc.) do que o pulso principal.
        # Retorna os índices dos frames onde onsets foram detectados.
        onset_frames = librosa.onset.onset_detect(onset_envelope=onset_envelope, sr=sr, units='frames')

        # Get the strength value at each detected onset frame
        # Ensure onset_frames are within the bounds of onset_envelope
        valid_onset_frames = [f for f in onset_frames if 0 <= f < len(onset_envelope)]
        onset_amplitudes = onset_envelope[valid_onset_frames]
        onset_times = librosa.frames_to_time(valid_onset_frames, sr=sr)


        if not onset_times.size > 0: # Verifica se foram detectados onsets válidos
            print(f"ℹ️ Nenhuma batida/onset marcante detectado em '{os.path.basename(caminho_audio)}'. Nenhum arquivo de batidas será gerado.")
            # Limpa a pasta de saída de batidas se ela existir, pois não há batidas válidas
            if os.path.exists(pasta_saida_batidas):
                 print(f"   Limpando pasta de análise de batidas (nenhuma batida detectada): {pasta_saida_batidas}")
                 try:
                     shutil.rmtree(pasta_saida_batidas)
                 except Exception as e:
                     print(f'⚠️ Falha ao deletar pasta {pasta_saida_batidas}. Razão: {e}')
            return None, None

        if not os.path.exists(pasta_saida_batidas):
            try:
                os.makedirs(pasta_saida_batidas, exist_ok=True)
            except OSError as e:
                print(f"⚠️ Erro ao criar pasta para arquivos de batidas {pasta_saida_batidas}: {e}")
                return None, None
        else:
            # Limpa a pasta de saída de batidas antes de escrever os novos arquivos
            print(f"   Limpando pasta de análise de batidas: {pasta_saida_batidas}")
            for filename in os.listdir(pasta_saida_batidas):
                file_path = os.path.join(pasta_saida_batidas, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f'⚠️ Falha ao deletar {file_path}. Razão: {e}')


        # Combine timestamps and amplitudes, filtering out negative times
        beat_data = []
        for t, amp in zip(onset_times, onset_amplitudes):
            if t >= 0:
                # Convert amplitude to float explicitly just in case
                beat_data.append({'timestamp_sec': t, 'timestamp_hhmmssff': format_seconds_to_hhmmssff(t, fps_para_timestamp), 'amplitude': float(amp)})

        if not beat_data:
             print(f"ℹ️ Nenhuma batida válida (tempo >= 0) detectada em '{os.path.basename(caminho_audio)}'. Nenhum arquivo de batidas será gerado.")
             return None, None

        # Save beats with amplitude
        arquivo_beats_with_amplitude = os.path.join(pasta_saida_batidas, "beats_with_amplitude.txt")
        with open(arquivo_beats_with_amplitude, "w", encoding='utf-8') as f_amp:
            for item in beat_data:
                # Format amplitude to a few decimal places for readability/consistency
                f_amp.write(f"{item['timestamp_hhmmssff']},{item['amplitude']:.6f}\n")

        # Save beats (timestamps only) - this will be the one potentially filtered later
        arquivo_saida_batidas = os.path.join(pasta_saida_batidas, "beats.txt")
        with open(arquivo_saida_batidas, "w", encoding='utf-8') as f_beats:
             for item in beat_data:
                 f_beats.write(f"{item['timestamp_hhmmssff']}\n")

        print(f"✅ Dados de batidas ({len(beat_data)} eventos) salvos:")
        print(f"   - Timestamps e amplitudes: {arquivo_beats_with_amplitude}")
        print(f"   - Apenas timestamps: {arquivo_saida_batidas}")
        return arquivo_saida_batidas, arquivo_beats_with_amplitude

    except Exception as e:
        print(f"⚠️ Erro ao analisar batidas de '{os.path.basename(caminho_audio)}': {e}")
        return None, None

def parse_hhmmssff_to_seconds(time_str, fps=25):
    """
    Converte uma string de tempo HH:MM:SS:FF para segundos.
    Args:
        time_str (str): String de tempo no formato HH:MM:SS:FF.
        fps (int): Taxa de quadros por segundo usada para o componente FF.
    Returns:
        float: Tempo total em segundos.
    """
    if not isinstance(fps, int) or fps <= 0:
        fps = 25 # Fallback para FPS padrão

    parts = time_str.split(':')
    if len(parts) != 4:
        # Tenta parsear como HH:MM:SS se FF não estiver presente
        if len(parts) == 3:
            parts.append("0") # Adiciona FF=0
        else:
            raise ValueError(f"Time string '{time_str}' deve estar no formato HH:MM:SS ou HH:MM:SS:FF")
    try:
        h, m, s, f = map(int, parts)
    except ValueError:
         raise ValueError(f"Componentes de tempo inválidos na string '{time_str}'.")

    return (h * 3600 + m * 60 + s) + (f / fps)

def find_frame_by_number(frames_dir, target_frame_number_str):
    """
    Encontra o arquivo de frame em frames_dir cujo número sequencial no nome
    corresponde a target_frame_number_str.
    Os nomes dos frames devem ser como 'frame_XXXXXX_...'.
    """
    if not os.path.exists(frames_dir):
        print(f"⚠️ Diretório de frames não encontrado: {frames_dir}")
        return None

    try:
        target_frame_number = int(target_frame_number_str) # Converte para inteiro para formatação
    except ValueError:
        print(f"⚠️ Número de frame inválido fornecido: '{target_frame_number_str}'. Deve ser um número inteiro.")
        return None

    # Formata o número do frame para ter 6 dígitos com zeros à esquerda, como no nome do arquivo
    search_prefix = f"frame_{target_frame_number:06d}_"

    for filename in os.listdir(frames_dir):
        if filename.startswith(search_prefix) and filename.lower().endswith(".jpg"): # Assumindo extensão .jpg
            frame_path = os.path.join(frames_dir, filename)
            # print(f"   Frame encontrado para o número '{target_frame_number_str}': {filename}") # Comentado para não quebrar a barra de progresso
            return frame_path
    else:
        print(f"⚠️ Nenhum frame correspondente encontrado para o número '{target_frame_number_str}' (prefixo buscado: '{search_prefix}') em {frames_dir}")

    return None

def criar_edite_do_json(edit_data):
    """
    Cria um vídeo editado com base nas especificações do arquivo JSON.
    """
    print("\n🎬 Iniciando criação do edit a partir de 'edit.json'...")

    videos_baixados_dir = "videos_baixados"
    songs_dir = "songs"
    temp_dir = "temp_edit_files"
    output_edit_filename = "edit_final.mp4"
    video_fps_output = 25 # FPS para os clipes de cena gerados e para parsear timestamps FF

    source_video_name = edit_data.get("source_video")
    source_audio_name = edit_data.get("source_audio")
    scenes_data = edit_data.get("scenes", [])

    if not source_video_name or not source_audio_name:
        print("⚠️ 'source_video' ou 'source_audio' não encontrado no edit.json.")
        return

    full_audio_path = os.path.join(songs_dir, source_audio_name)
    video_frames_dir_name = os.path.splitext(source_video_name)[0] + "_frames"
    full_video_frames_dir = os.path.join(videos_baixados_dir, video_frames_dir_name)

    if not os.path.exists(full_audio_path):
        print(f"⚠️ Arquivo de áudio fonte não encontrado: {full_audio_path}")
        return
    if not os.path.exists(full_video_frames_dir):
        print(f"⚠️ Diretório de frames do vídeo fonte não encontrado: {full_video_frames_dir}")
        return

    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir) # Remove diretório temporário antigo
    os.makedirs(temp_dir, exist_ok=True)

    scene_clip_paths = []

    total_scenes = len(scenes_data)
    print(f"  Total de cenas a processar: {total_scenes}")

    for i, scene in enumerate(scenes_data):
        # Barra de progresso simples
        progress = (i + 1) / total_scenes
        bar_length = 30
        filled_length = int(bar_length * progress)
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        print(f"\r  Processando cena {i+1}/{total_scenes} [{bar}] {progress*100:.1f}%", end="", flush=True)

        audio_start_str = scene.get("audio_start")
        audio_end_str = scene.get("audio_end")
        target_frame_number_str = scene.get("frame") # Agora é o número do frame

        if not all([audio_start_str, audio_end_str, target_frame_number_str]):
            print(f"⚠️ Dados incompletos para a cena {i+1}. Pulando.")
            continue

        try:
            audio_start_sec = parse_hhmmssff_to_seconds(audio_start_str, fps=video_fps_output)
            audio_end_sec = parse_hhmmssff_to_seconds(audio_end_str, fps=video_fps_output)
            # target_frame_sec = float(target_frame_timestamp_str) # Não é mais necessário converter para float
            # A validação do número do frame (se é um inteiro) pode ser adicionada se desejado
        except ValueError as e:
            print(f"⚠️ Erro ao converter timestamps para a cena {i+1}: {e}. Pulando.")
            continue

        audio_duration_sec = audio_end_sec - audio_start_sec
        if audio_duration_sec <= 0:
            print(f"⚠️ Duração do áudio inválida para a cena {i+1} ({audio_duration_sec}s). Pulando.")
            continue

        frame_image_path = find_frame_by_number(full_video_frames_dir, target_frame_number_str)
        if not frame_image_path:
            print(f"⚠️ Não foi possível encontrar o frame para a cena {i+1}. Pulando.")
            continue

        temp_audio_clip_path = os.path.join(temp_dir, f"scene_{i+1}_audio.aac") # Usar AAC para compatibilidade
        temp_video_clip_path = os.path.join(temp_dir, f"scene_{i+1}_video.mp4")

        # Cortar áudio
        cmd_audio = [
            "ffmpeg", "-y",
            "-i", full_audio_path,
            "-ss", str(audio_start_sec), # Output seeking, placed after -i
            "-t", str(audio_duration_sec), # Use duration instead of -to
            "-c:a", "aac", "-b:a", "192k", # Re-encoda para AAC
            temp_audio_clip_path
        ]
        # print(f"    Cortando áudio: {' '.join(cmd_audio)}") # Opcional: remover para limpar o output
        audio_process_result = subprocess.run(cmd_audio, capture_output=True, text=True)
        if audio_process_result.returncode != 0:
            print(f"⚠️ Erro ao cortar áudio para cena {i+1}:")
            print(f"   Comando: {' '.join(cmd_audio)}")
            print(f"   ffmpeg stdout: {audio_process_result.stdout}")
            print(f"   ffmpeg stderr: {audio_process_result.stderr}")
            continue # Pula para a próxima cena


        # Criar clipe de vídeo a partir do frame e do áudio cortado
        cmd_video_scene = [
            "ffmpeg", "-y", "-loop", "1", "-framerate", str(video_fps_output), "-i", frame_image_path,
            "-i", temp_audio_clip_path,
            "-c:v", "libx264", "-tune", "stillimage", "-c:a", "copy", # Copia o áudio já em AAC
            "-pix_fmt", "yuv420p", "-t", str(audio_duration_sec), "-shortest",
            temp_video_clip_path
        ]
        # print(f"    Criando clipe da cena: {' '.join(cmd_video_scene)}") # Opcional: remover para limpar o output
        video_scene_process_result = subprocess.run(cmd_video_scene, capture_output=True, text=True)
        if video_scene_process_result.returncode != 0:
            print(f"⚠️ Erro ao criar clipe da cena {i+1}:")
            print(f"   Comando: {' '.join(cmd_video_scene)}")
            print(f"   ffmpeg stdout: {video_scene_process_result.stdout}")
            print(f"   ffmpeg stderr: {video_scene_process_result.stderr}")
            continue # Pula para a próxima cena
        scene_clip_paths.append(temp_video_clip_path)

    print(flush=True) # Nova linha após a barra de progresso concluir e garantir flush
    if not scene_clip_paths:
        print("⚠️ Nenhuma cena foi processada. Edição final não será criada.")
        shutil.rmtree(temp_dir)
        return

    # Concatenar clipes de cena
    filelist_path = os.path.join(temp_dir, "filelist.txt")
    with open(filelist_path, "w") as f:
        for clip_path in scene_clip_paths:
            # ffmpeg concat demuxer requer caminhos relativos (ao filelist.txt) ou absolutos.
            # Para simplicidade, se os clipes estão no mesmo dir que filelist.txt, só o nome do arquivo.
            f.write(f"file '{os.path.basename(clip_path)}'\n")

    cmd_concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", filelist_path,
        "-c", "copy", output_edit_filename
    ]
    print(f"\n  Concatenando cenas para '{output_edit_filename}': {' '.join(cmd_concat)}")
    concat_process_result = subprocess.run(cmd_concat, capture_output=True, text=True)
    if concat_process_result.returncode == 0:
        print(f"✅ Edição final '{output_edit_filename}' criada com sucesso!")
    else:
        print(f"⚠️ Erro ao concatenar vídeos:")
        print(f"   Comando: {' '.join(cmd_concat)}")
        print(f"   ffmpeg stdout: {concat_process_result.stdout}")
        print(f"   ffmpeg stderr: {concat_process_result.stderr}")

    # Limpar arquivos temporários
    shutil.rmtree(temp_dir)
    print(f"  Diretório temporário '{temp_dir}' removido.")

def carregar_configuracao(caminho_arquivo_config="config.json"):
    """Carrega as configurações de um arquivo JSON."""
    config_padrao = {
        "baixar_videos_da_lista": True,
        "extrair_frames_dos_videos": True,
        "baixar_audio_da_musica": True,
        "analisar_batidas_do_audio": True,
        "filtrar_batidas_por_amplitude": { # Novo padrão
            "enabled": True,
            "min_amplitude_percentage": 75
        },
        "criar_edit_final_do_json": False,
        "generate_edit_from_beats": { # Agora é um objeto
            "enabled": False,
            "min_scene_duration_seconds": 2.0 # Valor padrão
        }
    }
    if os.path.exists(caminho_arquivo_config):
        try:
            with open(caminho_arquivo_config, "r", encoding='utf-8') as f:
                config_carregada = json.load(f)
                # Mescla com o padrão para garantir que todas as chaves existam
                # Handle potential old boolean format for generate_edit_from_beats
                config_padrao.update(config_carregada)

                # Ensure sub-structures are dictionaries and have expected keys, handling old formats
                if isinstance(config_padrao.get("generate_edit_from_beats"), bool): # Converte formato antigo
                    config_padrao["generate_edit_from_beats"] = {"enabled": config_padrao["generate_edit_from_beats"], "min_scene_duration_seconds": 2.0}
                elif not isinstance(config_padrao.get("generate_edit_from_beats"), dict): # Se não for bool nem dict, reseta
                    config_padrao["generate_edit_from_beats"] = {"enabled": False, "min_scene_duration_seconds": 2.0}

                # Handle potential old boolean format for filtrar_batidas_por_amplitude (if it ever existed as bool)
                if isinstance(config_padrao.get("filtrar_batidas_por_amplitude"), bool):
                     config_padrao["filtrar_batidas_por_amplitude"] = {"enabled": config_padrao["filtrar_batidas_por_amplitude"], "min_amplitude_percentage": 75}
                elif not isinstance(config_padrao.get("filtrar_batidas_por_amplitude"), dict):
                     config_padrao["filtrar_batidas_por_amplitude"] = {"enabled": True, "min_amplitude_percentage": 75}


                print(f"⚙️ Configurações carregadas de '{caminho_arquivo_config}'.")
                return config_padrao
        except json.JSONDecodeError as e:
            print(f"⚠️ Erro ao decodificar '{caminho_arquivo_config}': {e}. Usando configurações padrão.")
        except Exception as e:
            print(f"⚠️ Erro ao ler '{caminho_arquivo_config}': {e}. Usando configurações padrão.")
    else:
        print(f"ℹ️ Arquivo de configuração '{caminho_arquivo_config}' não encontrado. Usando configurações padrão.")
    return config_padrao

def gerar_edit_json_pelas_batidas(caminho_arquivo_batidas, pasta_frames_video_fonte, nome_video_fonte_no_json, nome_audio_fonte_no_json, min_duration_sec, caminho_saida_edit_json="edit.json"):
    """
    Gera um arquivo edit.json usando os tempos de um arquivo de batidas e frames aleatórios.
    """
    print(f"\n🔄 Gerando '{caminho_saida_edit_json}' a partir de batidas e frames aleatórios...")
    if not os.path.exists(caminho_arquivo_batidas):
        print(f"⚠️ Arquivo de batidas não encontrado: {caminho_arquivo_batidas}")
        return False
    if not os.path.exists(pasta_frames_video_fonte):
        print(f"⚠️ Pasta de frames do vídeo fonte não encontrada: {pasta_frames_video_fonte}")
        return False

    try:
        with open(caminho_arquivo_batidas, "r", encoding='utf-8') as f:
            beat_timestamps_hhmmssff = [line.strip() for line in f if line.strip()]

        if len(beat_timestamps_hhmmssff) < 2:
            print(f"⚠️ Não há batidas suficientes em '{caminho_arquivo_batidas}' para criar cenas (necessário >= 2).")
            return False

        available_frames_files = [f for f in os.listdir(pasta_frames_video_fonte) if f.startswith("frame_") and f.lower().endswith(".jpg")]
        if not available_frames_files:
            print(f"⚠️ Nenhum arquivo de frame encontrado em '{pasta_frames_video_fonte}'.")
            return False

        # Extrai os números dos frames dos nomes dos arquivos
        # Ex: frame_000023_time_1.23s.jpg -> "23"
        available_frame_numbers = []
        for frame_file in available_frames_files:
            try:
                parts = frame_file.split('_')
                if len(parts) > 1 and parts[0] == "frame":
                    # Converte para int e depois para str para remover zeros à esquerda
                    frame_num_str = str(int(parts[1]))
                    available_frame_numbers.append(frame_num_str)
            except (ValueError, IndexError):
                print(f"   Aviso: Não foi possível extrair o número do frame de '{frame_file}'. Pulando.")

        if not available_frame_numbers:
            print(f"⚠️ Nenhum número de frame válido pôde ser extraído dos arquivos em '{pasta_frames_video_fonte}'.")
            return False

        # min_duration_sec agora é passado como argumento
        # FPS usado para parsear os timestamps HH:MM:SS:FF do arquivo de batidas.
        # Deve ser consistente com o FPS usado ao gerar esse arquivo.
        fps_for_parsing = 25
        scenes = []
        i = 0
        while i < len(beat_timestamps_hhmmssff) - 1: # Precisa de pelo menos uma batida após i para formar uma cena
            audio_start_str = beat_timestamps_hhmmssff[i]
            suitable_audio_end_str = None

            # Procura por um audio_end_str que resulte em uma duração >= min_duration_sec
            next_beat_index_for_end = i + 1
            while next_beat_index_for_end < len(beat_timestamps_hhmmssff):
                potential_audio_end_str = beat_timestamps_hhmmssff[next_beat_index_for_end]

                try:
                    audio_start_sec = parse_hhmmssff_to_seconds(audio_start_str, fps=fps_for_parsing)
                    audio_end_sec = parse_hhmmssff_to_seconds(potential_audio_end_str, fps=fps_for_parsing)
                except ValueError as e:
                    print(f"   ⚠️ Erro ao parsear timestamp para cálculo de duração: {e}. Pulando batida final potencial '{potential_audio_end_str}'.")
                    next_beat_index_for_end += 1
                    continue

                duration_sec = audio_end_sec - audio_start_sec

                if duration_sec >= min_duration_sec:
                    suitable_audio_end_str = potential_audio_end_str
                    break # Encontrou um final adequado

                next_beat_index_for_end += 1 # Tenta a próxima batida como final potencial

            if suitable_audio_end_str:
                selected_frame_number = random.choice(available_frame_numbers)
                scenes.append({
                    "audio_start": audio_start_str,
                    "audio_end": suitable_audio_end_str,
                    "frame": selected_frame_number
                })
                # A próxima cena deve começar a partir da batida que foi usada como final da cena atual
                i = next_beat_index_for_end
            else:
                # Se nenhum final adequado foi encontrado para audio_start_str, avança para a próxima batida inicial potencial.
                print(f"   ℹ️ Não foi possível criar cena a partir de '{audio_start_str}' com duração >= {min_duration_sec}s. Tentando próxima batida inicial.")
                i += 1

        edit_data = {
            "source_video": nome_video_fonte_no_json,
            "source_audio": nome_audio_fonte_no_json,
            "scenes": scenes
        }

        with open(caminho_saida_edit_json, "w", encoding='utf-8') as f:
            json.dump(edit_data, f, indent=4, ensure_ascii=False)
        print(f"✅ '{caminho_saida_edit_json}' gerado com {len(scenes)} cenas.")
        return True
    except Exception as e:
        print(f"⚠️ Erro ao gerar '{caminho_saida_edit_json}' a partir das batidas: {e}")
        return False

# Exemplo de uso
if __name__ == "__main__":
    edit_json_file = "edit.json"
    config_geral_file = "config.json"

    # Carrega as configurações gerais
    config = carregar_configuracao(config_geral_file)
    print(f"Configurações de execução: {config}")

    arquivo_links = "links.txt"  # Coloque as URLs dos vídeos aqui, uma por linha
    pasta_destino_videos = "videos_baixados" # Pasta para salvar os vídeos e as pastas de frames
    intervalo_para_frames_seg = 1 # Extrair um frame a cada X segundos
    qualidade_dos_frames_jpeg = 75 # Qualidade JPEG (0-100), menor valor = menor tamanho/qualidade
    songs_directory = "songs" # Pasta onde as músicas estão localizadas
    musica_config_file = "musica.txt" # Arquivo que contém o nome do arquivo de música

    caminho_do_arquivo_de_musica = None
    youtube_url_musica = None
    # Variáveis para armazenar os caminhos dos arquivos de batidas gerados
    arquivo_beats_processado = None
    arquivo_beats_with_amplitude_processado = None

    # --- 1. Obter URL da música (se download de áudio ou análise de batidas estiverem habilitados) ---
    if config.get("baixar_audio_da_musica") or config.get("analisar_batidas_do_audio"):
        if not os.path.exists(musica_config_file):
            print(f"⚠️ Arquivo '{musica_config_file}' não encontrado. Não será possível processar áudio.")
        else:
            try:
                with open(musica_config_file, "r", encoding='utf-8') as f_music_config:
                    youtube_url_musica = f_music_config.readline().strip()
                if not youtube_url_musica:
                    print(f"⚠️ Arquivo '{musica_config_file}' está vazio.")
                    youtube_url_musica = None
                elif not (youtube_url_musica.startswith("http://") or youtube_url_musica.startswith("https://")):
                    print(f"⚠️ Conteúdo de '{musica_config_file}' ('{youtube_url_musica}') não parece ser uma URL válida.")
                    youtube_url_musica = None
            except Exception as e:
                print(f"⚠️ Erro ao ler '{musica_config_file}': {e}")
                youtube_url_musica = None

    # --- 2. Processamento de Áudio (Download ou Localização) ---
    if youtube_url_musica:
        # Garante que a pasta 'songs' exista para download ou localização
        if not os.path.exists(songs_directory):
            try:
                os.makedirs(songs_directory, exist_ok=True)
            except OSError as e:
                print(f"⚠️ Erro ao criar pasta '{songs_directory}/': {e}. Processamento de áudio pode falhar.")
                youtube_url_musica = None # Impede prosseguimento se a pasta é crucial

        if youtube_url_musica and config.get("baixar_audio_da_musica"):
            print(f"\n🎵 Tentando baixar áudio de: {youtube_url_musica}")
            caminho_do_arquivo_de_musica, _ = baixar_audio_youtube(youtube_url_musica, songs_directory)
            if caminho_do_arquivo_de_musica:
                print(f"🎶 Áudio baixado/localizado via download: {caminho_do_arquivo_de_musica}")
            else:
                print(f"⚠️ Falha ao baixar o áudio de '{youtube_url_musica}'.")

        # Se o download não foi habilitado OU falhou, mas a análise de batidas está habilitada, tenta localizar.
        if not caminho_do_arquivo_de_musica and youtube_url_musica and config.get("analisar_batidas_do_audio"):
            if not config.get("baixar_audio_da_musica"): # Informa que está localizando porque download está off
                print(f"\n🎵 Download de áudio desabilitado. Tentando localizar áudio para análise...")
            # Se chegou aqui após falha de download, a msg de falha já foi impressa.

            caminho_esperado_musica = resolver_nome_arquivo_yt_dlp(youtube_url_musica, songs_directory, extrair_audio=True)
            if caminho_esperado_musica and os.path.exists(caminho_esperado_musica):
                caminho_do_arquivo_de_musica = caminho_esperado_musica
                print(f"🎶 Áudio localizado para análise: {caminho_do_arquivo_de_musica}")
            else:
                print(f"⚠️ Áudio não encontrado localmente em '{songs_directory}' para a URL '{youtube_url_musica}'.")
                if caminho_esperado_musica:
                     print(f"   Caminho esperado (não encontrado): {caminho_esperado_musica}")
    elif config.get("baixar_audio_da_musica") or config.get("analisar_batidas_do_audio"):
        print("\nℹ️ Nenhuma URL de música válida fornecida em '{musica_config_file}'. Processamento de áudio pulado.")

    # --- 3. Análise de Batidas (se habilitada e áudio disponível) ---
    if config.get("analisar_batidas_do_audio"):
        # Verifica se librosa está instalado antes de tentar analisar
        try:
            import librosa
            import numpy as np
            librosa_disponivel = True
        except ImportError:
            librosa_disponivel = False
            print("\n⚠️ Análise de batidas desabilitada: librosa ou numpy não está instalado.")
            print("   Por favor, instale com: pip install librosa numpy")


        if librosa_disponivel:
            audio_para_analise_encontrado = None
            # Tenta encontrar um arquivo de áudio na pasta 'songs'
            if os.path.exists(songs_directory) and os.path.isdir(songs_directory):
                audio_extensions = ('.mp3', '.wav', '.aac', '.m4a', '.ogg', '.flac')
                for f_name in sorted(os.listdir(songs_directory)): # sorted para consistência
                    if os.path.isfile(os.path.join(songs_directory, f_name)) and f_name.lower().endswith(audio_extensions):
                        audio_para_analise_encontrado = os.path.join(songs_directory, f_name)
                        print(f"\n🎵 Áudio encontrado para análise de batidas: {audio_para_analise_encontrado}")
                        break

            if audio_para_analise_encontrado:
                fps_referencia_batidas = 25
                pasta_batidas_analisadas = os.path.join(songs_directory, "analise_batidas")
                # A função analisar_batidas_audio agora vai limpar a pasta e nomear o arquivo como beats.txt
                arquivo_beats_processado, arquivo_beats_with_amplitude_processado = analisar_batidas_audio(audio_para_analise_encontrado, pasta_batidas_analisadas, fps_para_timestamp=fps_referencia_batidas)
                # As mensagens de sucesso ou falha já são impressas dentro da função
            else:
                print(f"ℹ️ Análise de batidas pulada: nenhum arquivo de áudio encontrado na pasta '{songs_directory}'.")
        # else: (mensagem de librosa não disponível já foi impressa)
    else:
        print("\nℹ️ Análise de batidas do áudio desabilitada nas configurações.")

    # --- 3.1. Filtragem de Batidas por Amplitude (se habilitada) ---
    filter_config = config.get("filtrar_batidas_por_amplitude", {})
    # Verifica se a configuração é um dicionário e se 'enabled' é True
    if isinstance(filter_config, dict) and filter_config.get("enabled"):
        print("\n⚙️ Tentando filtrar batidas por amplitude...")
        # Check if the necessary files were generated by the analysis step
        if arquivo_beats_processado and arquivo_beats_with_amplitude_processado and os.path.exists(arquivo_beats_processado) and os.path.exists(arquivo_beats_with_amplitude_processado):
            min_amp_percentage = filter_config.get("min_amplitude_percentage", 75)
            print(f"   Carregando dados de amplitude de '{os.path.basename(arquivo_beats_with_amplitude_processado)}'...")
            timestamp_to_amplitude_map, overall_max_amplitude = load_amplitude_data(arquivo_beats_with_amplitude_processado)

            if timestamp_to_amplitude_map and overall_max_amplitude > 0:
                print(f"   Maior amplitude geral encontrada: {overall_max_amplitude:.6f}")
                print(f"   Limite inferior para filtro ({min_amp_percentage}%): {(min_amp_percentage / 100.0) * overall_max_amplitude:.6f}")
                # This function overwrites the beats.txt file with filtered results
                filter_timestamps_by_amplitude(
                    arquivo_beats_processado, # This is the beats.txt file to be overwritten
                    timestamp_to_amplitude_map,
                    overall_max_amplitude,
                    min_amp_percentage
                )
            else:
                print("   ⚠️ Não foi possível carregar dados de amplitude válidos. Filtragem por amplitude pulada.")
        else:
            print("   ⚠️ Arquivos de batidas necessários para filtragem não encontrados. Filtragem por amplitude pulada.")
    else:
        print("\nℹ️ Filtragem de batidas por amplitude desabilitada nas configurações.")


    # --- 4. Processamento de Vídeos (Download ou Localização) e Extração de Frames ---
    processar_videos_geral = config.get("baixar_videos_da_lista") or config.get("extrair_frames_dos_videos")
    primeiro_video_com_frames_path = None
    primeiro_video_com_frames_nome_base = None

    if processar_videos_geral:
        if not os.path.exists(arquivo_links):
            print(f"\n⚠️ Arquivo de links '{arquivo_links}' não encontrado.")
            print("   Processamento de vídeos e extração de frames pulados.")
        else:
            with open(arquivo_links, "r", encoding='utf-8') as f_links:
                links_videos = [linha.strip() for linha in f_links if linha.strip() and not linha.startswith("#")]

            if not links_videos:
                print(f"Nenhum link de vídeo válido encontrado em '{arquivo_links}'.")
            else:
                print(f"\n▶️ Iniciando processamento de vídeos de '{arquivo_links}'...")
                if not os.path.exists(pasta_destino_videos): # Garante que a pasta de destino principal exista
                    try:
                        os.makedirs(pasta_destino_videos, exist_ok=True)
                        print(f"Pasta principal de vídeos '{pasta_destino_videos}' criada.")
                    except OSError as e:
                        print(f"⚠️ Erro ao criar pasta principal '{pasta_destino_videos}': {e}. Processamento de vídeos pode falhar.")
                        # Decide se quer pular todos os vídeos ou tentar mesmo assim

                for link_video in links_videos:
                    print(f"\n--- Processando link: {link_video} ---")
                    caminho_video_final_para_frames = None

                    if config.get("baixar_videos_da_lista"):
                        caminho_video_baixado, _ = baixar_video(link_video, pasta_destino_videos)
                        if caminho_video_baixado:
                            caminho_video_final_para_frames = caminho_video_baixado
                            print(f"🎞️ Vídeo baixado/localizado via download: {caminho_video_final_para_frames}")
                        else:
                            print(f"⚠️ Falha ao baixar vídeo de '{link_video}'.")

                    if not caminho_video_final_para_frames and config.get("extrair_frames_dos_videos"):
                        if not config.get("baixar_videos_da_lista"):
                             print(f"🎞️ Download de vídeo desabilitado. Tentando localizar vídeo para extração de frames...")

                        caminho_esperado_video = resolver_nome_arquivo_yt_dlp(link_video, pasta_destino_videos, extrair_audio=False)
                        if caminho_esperado_video and os.path.exists(caminho_esperado_video):
                            caminho_video_final_para_frames = caminho_esperado_video
                            print(f"🎞️ Vídeo localizado para extração: {caminho_video_final_para_frames}")
                        else:
                            print(f"⚠️ Vídeo não encontrado localmente em '{pasta_destino_videos}' para o link '{link_video}'.")
                            if caminho_esperado_video:
                                print(f"   Caminho esperado (não encontrado): {caminho_esperado_video}")

                    if caminho_video_final_para_frames and os.path.exists(caminho_video_final_para_frames) and config.get("extrair_frames_dos_videos"):
                        nome_base_video = os.path.splitext(os.path.basename(caminho_video_final_para_frames))[0]
                        pasta_frames_video = os.path.join(pasta_destino_videos, f"{nome_base_video}_frames")

                        # Guarda o primeiro vídeo que teve frames extraídos/localizados para usar no generate_edit_from_beats
                        if not primeiro_video_com_frames_path and os.path.exists(pasta_frames_video):
                            # Verifica se a pasta de frames realmente contém frames
                            if any(f.startswith("frame_") and f.lower().endswith(".jpg") for f in os.listdir(pasta_frames_video)):
                                primeiro_video_com_frames_path = pasta_frames_video
                                primeiro_video_com_frames_nome_base = os.path.basename(caminho_video_final_para_frames) # Ex: "video.mp4"
                                print(f"   📹 Vídeo '{primeiro_video_com_frames_nome_base}' com frames em '{primeiro_video_com_frames_path}' será usado para 'generate_edit_from_beats' se habilitado.")

                        frames_info = extrair_frames(caminho_video_final_para_frames, pasta_frames_video, intervalo_para_frames_seg, qualidade_dos_frames_jpeg)
                        if frames_info:
                            print(f"🎞️ Frames de '{nome_base_video}' extraídos com sucesso.")
                            # Se este é o primeiro vídeo com frames e ainda não foi definido, defina-o
                            if not primeiro_video_com_frames_path:
                                primeiro_video_com_frames_path = pasta_frames_video
                                primeiro_video_com_frames_nome_base = os.path.basename(caminho_video_final_para_frames)
                                print(f"   📹 Vídeo '{primeiro_video_com_frames_nome_base}' com frames em '{primeiro_video_com_frames_path}' será usado para 'generate_edit_from_beats' se habilitado.")
                        # extrair_frames já lida com logs de erro ou nenhum frame extraído
                    elif config.get("extrair_frames_dos_videos"): # Se extração habilitada mas vídeo não disponível
                        print(f"ℹ️ Extração de frames pulada para '{link_video}': arquivo de vídeo não disponível.")
    elif not config.get("criar_edit_final_do_json"): # Só imprime se nenhuma outra ação principal foi habilitada
        print("\nℹ️ Download de vídeos e extração de frames desabilitados nas configurações.")

    # --- 5. Gerar edit.json a partir das batidas (se habilitado) ---
    generate_edit_config = config.get("generate_edit_from_beats", {})
    if isinstance(generate_edit_config, dict) and generate_edit_config.get("enabled"):
        print("\n⚙️ Tentando gerar 'edit.json' a partir de arquivos existentes (batidas e frames)...")
        min_scene_duration = generate_edit_config.get("min_scene_duration_seconds", 2.0) # Pega do config ou usa default

        caminho_batidas_a_usar = None
        nome_audio_para_json = None
        pasta_frames_a_usar = None
        nome_video_para_json = None

        # A. Determinar arquivo de batidas (.txt) a partir de 'songs/analise_batidas'
        pasta_batidas_dir = os.path.join(songs_directory, "analise_batidas")
        # Agora buscamos especificamente por beats.txt, que é o arquivo potencialmente filtrado
        caminho_beats_txt_esperado = os.path.join(pasta_batidas_dir, "beats.txt")
        if os.path.exists(caminho_beats_txt_esperado):
             caminho_batidas_a_usar = caminho_beats_txt_esperado
             print(f"   🎶 Usando arquivo de batidas: {caminho_batidas_a_usar}")
        else:
            print(f"   ⚠️ Arquivo de batidas '{caminho_beats_txt_esperado}' não encontrado.")


        # B. Determinar nome do áudio para JSON a partir da pasta 'songs'
        if os.path.exists(songs_directory) and os.path.isdir(songs_directory):
            audio_extensions = ('.mp3', '.wav', '.aac', '.m4a', '.ogg', '.flac')
            for f_name in sorted(os.listdir(songs_directory)):
                if os.path.isfile(os.path.join(songs_directory, f_name)) and f_name.lower().endswith(audio_extensions):
                    nome_audio_para_json = f_name
                    print(f"   🎵 Usando primeiro arquivo de áudio encontrado em '{songs_directory}': {nome_audio_para_json}")
                    break
        if not nome_audio_para_json:
            print(f"   ⚠️ Nenhum arquivo de áudio ({', '.join(audio_extensions)}) encontrado em '{songs_directory}'.")

        # C. Determinar pasta de frames do vídeo a partir de 'videos_baixados'
        if os.path.exists(pasta_destino_videos) and os.path.isdir(pasta_destino_videos):
            for entry_name in sorted(os.listdir(pasta_destino_videos)):
                potential_frames_dir = os.path.join(pasta_destino_videos, entry_name)
                if os.path.isdir(potential_frames_dir) and entry_name.lower().endswith("_frames"):
                    # Verificar se a pasta contém arquivos .jpg
                    if any(f.lower().endswith(".jpg") for f in os.listdir(potential_frames_dir) if os.path.isfile(os.path.join(potential_frames_dir, f))):
                        pasta_frames_a_usar = potential_frames_dir
                        print(f"   🖼️ Usando primeira pasta de frames (com .jpg e terminada em '_frames') encontrada: {pasta_frames_a_usar}")
                        break
        if not pasta_frames_a_usar:
            print(f"   ⚠️ Nenhuma pasta de frames (terminada em '_frames' e contendo .jpg) encontrada em '{pasta_destino_videos}'.")

        # D. Determinar nome do vídeo para JSON a partir de 'videos_baixados'
        if os.path.exists(pasta_destino_videos) and os.path.isdir(pasta_destino_videos):
            video_extensions = ('.mp4', '.webm', '.mkv', '.avi', '.mov')
            for f_name in sorted(os.listdir(pasta_destino_videos)):
                if os.path.isfile(os.path.join(pasta_destino_videos, f_name)) and f_name.lower().endswith(video_extensions):
                    nome_video_para_json = f_name
                    print(f"   🎞️ Usando primeiro arquivo de vídeo encontrado em '{pasta_destino_videos}': {nome_video_para_json}")
                    break
        if not nome_video_para_json:
            print(f"   ⚠️ Nenhum arquivo de vídeo ({', '.join(video_extensions)}) encontrado em '{pasta_destino_videos}'.")

        # E. Gerar JSON se todos os componentes foram encontrados/determinados
        if caminho_batidas_a_usar and pasta_frames_a_usar and nome_video_para_json and nome_audio_para_json:
            # Check if the beats file is empty after potential filtering
            try:
                with open(caminho_batidas_a_usar, 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                    if not first_line:
                        print(f"⚠️ Arquivo de batidas '{caminho_batidas_a_usar}' está vazio após a filtragem. Não é possível gerar 'edit.json'.")
                        caminho_batidas_a_usar = None # Marca como não utilizável
            except Exception as e:
                 print(f"⚠️ Erro ao ler arquivo de batidas '{caminho_batidas_a_usar}': {e}. Não é possível gerar 'edit.json'.")
                 caminho_batidas_a_usar = None # Marca como não utilizável


        if caminho_batidas_a_usar and pasta_frames_a_usar and nome_video_para_json and nome_audio_para_json:
             gerar_edit_json_pelas_batidas(
                 caminho_batidas_a_usar,
                 pasta_frames_a_usar,
                 nome_video_para_json,
                 nome_audio_para_json,
                 min_scene_duration,
                 edit_json_file
             )
        else:
            print("⚠️ Não foi possível gerar 'edit.json' a partir das batidas: um ou mais arquivos/pastas necessários não foram encontrados ou determinados.")
            if not caminho_batidas_a_usar: print("      - Arquivo de batidas não determinado/encontrado ou vazio.") # Updated message
            if not pasta_frames_a_usar: print("      - Pasta de frames não determinada/encontrada ou vazia.")
            if not nome_video_para_json: print("      - Nome do vídeo para JSON não determinado.") # Updated message
            if not nome_audio_para_json: print("      - Nome do áudio para JSON não determinado.")
    else:
        print("\nℹ️ Geração de 'edit.json' a partir das batidas desabilitada nas configurações.")

    # --- 6. Lógica para criar o edit final a partir do edit.json (se habilitado) ---
    # Esta etapa agora pode usar o edit.json gerado na etapa anterior ou um existente.
    if config.get("criar_edit_final_do_json", False):
        if os.path.exists(edit_json_file):
            print(f"\nℹ️ Arquivo '{edit_json_file}' encontrado. Tentando criar edit final...")
            try:
                with open(edit_json_file, "r", encoding='utf-8') as f:
                    conteudo_edit = json.load(f)
                criar_edite_do_json(conteudo_edit)
            except json.JSONDecodeError as e:
                print(f"⚠️ Erro ao decodificar '{edit_json_file}': {e}. Não será possível criar o edit.")
            except Exception as e:
                print(f"⚠️ Erro ao processar '{edit_json_file}' para criação do edit: {e}")
        else:
            print(f"⚠️ Arquivo '{edit_json_file}' não encontrado. Criação do edit final pulada.")
    if not config.get("criar_edit_final_do_json"):
         print("\nℹ️ Criação do edit final desabilitada nas configurações.")

    print("\n🏁 Processo concluído.")
    try:
        system_os = platform.system()
        played_custom_sound = False
        if system_os == "Darwin":  # macOS
            # Tenta tocar um som de sistema mais chamativo no macOS
            # Lista de sons em ordem de preferência (mais chamativo primeiro)
            preferred_sounds = [
                "/System/Library/Sounds/Hero.aiff",
                "/System/Library/Sounds/Hero.aiff",
                "/System/Library/Sounds/Hero.aiff",
                "/System/Library/Sounds/Hero.aiff",
                "/System/Library/Sounds/Glass.aiff" # O anterior como fallback
            ]
            for sound_file_path in preferred_sounds:
                if os.path.exists(sound_file_path):
                    subprocess.run(["afplay", sound_file_path], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    played_custom_sound = True
                    # break # Remove break to play all preferred sounds if available
        # For other OS or if no preferred sound was played on macOS, play the bell sound
        if not played_custom_sound:
             # Para Linux, Windows e outros, ou como fallback no macOS
             # Emite o som de sino (BEL) múltiplas vezes para ser mais chamativo
             for _ in range(3): # Repete 3 vezes
                 print('\a', end='', flush=True) # end='' e flush=True para tentar garantir emissão imediata
                 time.sleep(0.3) # Pequena pausa entre os sinos
    except Exception:
        print('\a')  # Fallback final para qualquer erro durante a tentativa de tocar som
