import os
import subprocess
import time # Adicionado para a pausa entre tentativas
import cv2 # Adicionado para manipulação de vídeo
from dotenv import load_dotenv # Adicionado para carregar o .env
import json # Adicionado para ler o arquivo edit.json
import shutil # Adicionado para remover diretório temporário

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

def parse_hhmmss_to_seconds(time_str):
    """Converte uma string de tempo HH:MM:SS para segundos."""
    h, m, s = map(int, time_str.split(':'))
    return h * 3600 + m * 60 + s

def find_frame_by_number(frames_dir, target_frame_number_str):
    """
    Encontra o arquivo de frame em frames_dir cujo número sequencial no nome
    corresponde a target_frame_number_str.
    Os nomes dos frames devem ser como 'frame_XXXXXX_...'.
    """
    if not os.path.exists(frames_dir):
        print(f"⚠️ Diretório de frames não encontrado: {frames_dir}")
        return None

    target_frame_number = int(target_frame_number_str) # Converte para inteiro para formatação
    # Formata o número do frame para ter 6 dígitos com zeros à esquerda, como no nome do arquivo
    search_prefix = f"frame_{target_frame_number:06d}_"

    for filename in os.listdir(frames_dir):
        if filename.startswith(search_prefix) and filename.endswith(".jpg"): # Assumindo extensão .jpg
            frame_path = os.path.join(frames_dir, filename)
            print(f"   Frame encontrado para o número '{target_frame_number_str}': {filename}")
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
    video_fps_output = "25" # FPS para os clipes de cena gerados

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

    for i, scene in enumerate(scenes_data):
        print(f"\n  Processando cena {i+1}...")
        audio_start_str = scene.get("audio_start")
        audio_end_str = scene.get("audio_end")
        target_frame_number_str = scene.get("frame") # Agora é o número do frame

        if not all([audio_start_str, audio_end_str, target_frame_number_str]):
            print(f"⚠️ Dados incompletos para a cena {i+1}. Pulando.")
            continue

        try:
            audio_start_sec = parse_hhmmss_to_seconds(audio_start_str)
            audio_end_sec = parse_hhmmss_to_seconds(audio_end_str)
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
        print(f"    Cortando áudio: {' '.join(cmd_audio)}")
        audio_process_result = subprocess.run(cmd_audio, capture_output=True, text=True)
        if audio_process_result.returncode != 0:
            print(f"⚠️ Erro ao cortar áudio para cena {i+1}:")
            print(f"   Comando: {' '.join(cmd_audio)}")
            print(f"   ffmpeg stdout: {audio_process_result.stdout}")
            print(f"   ffmpeg stderr: {audio_process_result.stderr}")
            continue # Pula para a próxima cena


        # Criar clipe de vídeo a partir do frame e do áudio cortado
        cmd_video_scene = [
            "ffmpeg", "-y", "-loop", "1", "-framerate", video_fps_output, "-i", frame_image_path,
            "-i", temp_audio_clip_path,
            "-c:v", "libx264", "-tune", "stillimage", "-c:a", "copy", # Copia o áudio já em AAC
            "-pix_fmt", "yuv420p", "-t", str(audio_duration_sec), "-shortest",
            temp_video_clip_path
        ]
        print(f"    Criando clipe da cena: {' '.join(cmd_video_scene)}")
        video_scene_process_result = subprocess.run(cmd_video_scene, capture_output=True, text=True)
        if video_scene_process_result.returncode != 0:
            print(f"⚠️ Erro ao criar clipe da cena {i+1}:")
            print(f"   Comando: {' '.join(cmd_video_scene)}")
            print(f"   ffmpeg stdout: {video_scene_process_result.stdout}")
            print(f"   ffmpeg stderr: {video_scene_process_result.stderr}")
            continue # Pula para a próxima cena
        scene_clip_paths.append(temp_video_clip_path)

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

def baixar_videos_da_lista(arquivo_lista, path_destino_videos_param=".", intervalo_extracao_frames_seg=1, qualidade_jpeg_frames=75, caminho_musica=None):
    if not os.path.exists(arquivo_lista):
        print(f"Arquivo de lista não encontrado: {arquivo_lista}")
        return
    
    if not os.path.exists(path_destino_videos_param):
        try:
            os.makedirs(path_destino_videos_param)
            print(f"Pasta de destino principal para vídeos criada: {path_destino_videos_param}")
        except OSError as e:
            print(f"⚠️ Erro ao criar pasta de destino principal para vídeos {path_destino_videos_param}: {e}")
            return
            
    with open(arquivo_lista, "r", encoding='utf-8') as f: # Adicionado encoding
        links = [linha.strip() for linha in f if linha.strip() and not linha.startswith("#")] # Ignora linhas vazias e comentários
    
    if not links:
        print(f"Nenhum link encontrado em {arquivo_lista}.")
        return

    print(f"\nIniciando download de {len(links)} vídeo(s) da lista '{arquivo_lista}'...")
    for link in links:
        # Verifica se a linha do link já está comentada antes de tentar baixar
        if link.strip().startswith("#"):
            print(f"ℹ️ Link já comentado, pulando: {link.strip()}")
            continue
        caminho_video_baixado, _ = baixar_video(link, path_destino_videos_param) # video_ja_existia not directly used here anymore
        
        if caminho_video_baixado:
            # Criar uma pasta específica para os frames deste vídeo
            nome_base_video = os.path.splitext(os.path.basename(caminho_video_baixado))[0]
            pasta_frames_video = os.path.join(path_destino_videos_param, f"{nome_base_video}_frames")
            
            frames_info = extrair_frames(caminho_video_baixado, pasta_frames_video, intervalo_extracao_frames_seg, qualidade_jpeg_frames)
            
            if frames_info:
                print(f"🎞️ Frames de '{nome_base_video}' extraídos.")
                if caminho_musica and os.path.exists(caminho_musica):
                    print(f"🎶 Música para análise: {caminho_musica}") # Apenas informa que a música está disponível
                    # A análise com LLM foi removida. Você pode adicionar sua própria lógica aqui.
                elif caminho_musica:
                    print(f"⚠️ Música especificada ({caminho_musica}) não encontrada. Análise com música não será possível para este vídeo.")
            # else: (extrair_frames já imprime erros ou status de nenhum frame)
        else:
            print(f"Download de {link} falhou ou foi pulado. Não será possível extrair frames.")
        print("-" * 30) # Separador entre vídeos

# Exemplo de uso
if __name__ == "__main__":
    edit_json_file = "edit.json"

    # Verifica se o arquivo edit.json existe
    if os.path.exists(edit_json_file):
        print(f"ℹ️ Arquivo '{edit_json_file}' encontrado.")
        try:
            with open(edit_json_file, "r", encoding='utf-8') as f:
                conteudo_edit = json.load(f) # Carrega o conteúdo JSON
            print("\nConteúdo de 'edit.json':")
            print(json.dumps(conteudo_edit, indent=4, ensure_ascii=False)) # Imprime de forma formatada
            criar_edite_do_json(conteudo_edit) # Chama a nova função para criar o edit
        except json.JSONDecodeError as e:
            print(f"⚠️ Erro ao decodificar '{edit_json_file}': {e}. O arquivo pode não ser um JSON válido.")
            exit("Programa finalizado devido a erro no 'edit.json'.")
        except Exception as e:
            print(f"⚠️ Erro ao ler '{edit_json_file}': {e}")
            exit("Programa finalizado devido a erro ao processar 'edit.json'.")
        exit("Programa finalizado após ler 'edit.json'.") # Encerra o programa

    arquivo_links = "links.txt"  # Coloque as URLs dos vídeos aqui, uma por linha
    pasta_destino_videos = "videos_baixados" # Pasta para salvar os vídeos e as pastas de frames
    intervalo_para_frames_seg = 1 # Extrair um frame a cada X segundos
    qualidade_dos_frames_jpeg = 75 # Qualidade JPEG (0-100), menor valor = menor tamanho/qualidade
    
    songs_directory = "songs" # Pasta onde as músicas estão localizadas
    musica_config_file = "musica.txt" # Arquivo que contém o nome do arquivo de música

    # Cria a pasta de destino principal para vídeos se não existir
    if not os.path.exists(pasta_destino_videos):
        try:
            os.makedirs(pasta_destino_videos)
            print(f"Pasta principal '{pasta_destino_videos}' criada.")
        except OSError as e:
            print(f"⚠️ Erro ao criar pasta principal '{pasta_destino_videos}': {e}")
            exit() # Sai se não puder criar a pasta principal

    # Verifica se o arquivo de links existe
    if not os.path.exists(arquivo_links):
        print(f"⚠️ Arquivo de links '{arquivo_links}' não encontrado.")
        print("Crie este arquivo e adicione as URLs dos vídeos do YouTube, uma por linha.")
        # Opcional: criar um arquivo de exemplo se não existir
        # with open(arquivo_links, "w", encoding='utf-8') as f_example:
        #     f_example.write("# Cole as URLs dos vídeos do YouTube aqui, uma por linha\n")
        #     f_example.write("# Exemplo:\n")
        #     f_example.write("# https://www.youtube.com/watch?v=dQw4w9WgXcQ\n")
        # print(f"Um arquivo de exemplo '{arquivo_links}' foi criado. Adicione suas URLs.")
        exit()

    # Determina o caminho do arquivo de música
    caminho_do_arquivo_de_musica = None
    # Garante que a pasta 'songs' exista
    if not os.path.exists(songs_directory):
        try:
            os.makedirs(songs_directory)
            print(f"Pasta '{songs_directory}/' criada.")
        except OSError as e:
            print(f"⚠️ Erro ao criar pasta '{songs_directory}/': {e}. Não será possível baixar a música.")
            # Prossegue sem música se a pasta não puder ser criada

    if not os.path.exists(musica_config_file):
        print(f"⚠️ Arquivo de configuração da música '{musica_config_file}' não encontrado.")
        print("   Não será possível carregar uma música para análise.")
    else:
        try:
            with open(musica_config_file, "r", encoding='utf-8') as f_music_config:
                youtube_url_musica = f_music_config.readline().strip()
            
            if not youtube_url_musica:
                print(f"⚠️ O arquivo '{musica_config_file}' está vazio ou não contém uma URL do YouTube válida.")
                print("   Não será possível carregar uma música para análise.")
            elif not (youtube_url_musica.startswith("http://") or youtube_url_musica.startswith("https://")):
                print(f"⚠️ Conteúdo de '{musica_config_file}' ('{youtube_url_musica}') não parece ser uma URL válida.")
                print("   Não será possível carregar uma música para análise.")
            else:
                print(f"Tentando baixar áudio da URL em '{musica_config_file}': {youtube_url_musica}")
                # Baixa o áudio da URL para a pasta 'songs'
                caminho_do_arquivo_de_musica, _ = baixar_audio_youtube( # musica_ja_existia not directly used here
                    youtube_url_musica, 
                    songs_directory
                )
                if caminho_do_arquivo_de_musica:
                    print(f"🎶 Áudio para análise: {caminho_do_arquivo_de_musica}")
                else:
                    print(f"⚠️ Falha ao baixar o áudio de '{youtube_url_musica}'.")
                    print("   A análise de combinação com música não será possível.")

        except Exception as e:
            print(f"⚠️ Erro ao ler o arquivo de configuração da música '{musica_config_file}': {e}")

    baixar_videos_da_lista(arquivo_links, pasta_destino_videos, intervalo_para_frames_seg, qualidade_dos_frames_jpeg, caminho_do_arquivo_de_musica)
    print("\nProcesso concluído.")
