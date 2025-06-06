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

from audio_processing import ( # Importa funções de processamento de áudio
    analisar_batidas_audio,
    load_amplitude_data,
    filter_timestamps_by_amplitude
)
from video_processing import ( # Importa funções de processamento de vídeo
    baixar_video,
    extrair_frames,
    detectar_cortes_de_cena # Nova função importada
)
from utils import resolver_nome_arquivo_yt_dlp, format_seconds_to_hhmmssff # Importa utilitários


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

def get_audio_duration(audio_path):
    """
    Obtém a duração de um arquivo de áudio usando ffprobe.
    Retorna a duração em segundos como float, ou None em caso de erro.
    """
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Erro ao obter duração de '{audio_path}': {e.stderr}")
    except FileNotFoundError:
        print("Erro: ffprobe não encontrado. Certifique-se de que o FFmpeg (com ffprobe) está instalado e no PATH.")
    except ValueError:
        print(f"Erro: Não foi possível converter a duração de '{audio_path}' para float.")
    return None

def criar_edite_do_json(edit_data, config):
    """
    Cria um vídeo editado com base nas especificações do arquivo JSON.
    """
    print("\n🎬 Iniciando criação do edit a partir de 'edit.json'...")

    videos_baixados_dir = "videos_baixados"
    songs_dir = "songs"
    temp_dir = "temp_edit_files"
    # output_edit_filename = "edit_final.mp4" # Removido pois agora é por qualidade
    video_fps_output = 25 # FPS para os clipes de cena gerados e para parsear timestamps FF

    source_video_name = edit_data.get("source_video")
    source_audio_name = edit_data.get("source_audio")
    scenes_data = edit_data.get("scenes", [])
    all_detected_scenes_data = None # Para carregar uma vez se necessário

    if not source_video_name or not source_audio_name:
        print("⚠️ 'source_video' ou 'source_audio' não encontrado no edit.json.")
        return

    full_audio_path = os.path.join(songs_dir, source_audio_name)
    video_frames_dir_name = os.path.splitext(source_video_name)[0] + "_frames"
    full_video_frames_dir = os.path.join(videos_baixados_dir, video_frames_dir_name)
    full_source_video_path = os.path.join(videos_baixados_dir, source_video_name)

    if not os.path.exists(full_audio_path):
        print(f"⚠️ Arquivo de áudio fonte não encontrado: {full_audio_path}")
        return
    # O diretório de frames só é necessário se estivermos usando frames.
    # O vídeo fonte original é necessário se estivermos usando scene_cuted.
    if not os.path.exists(full_source_video_path):
        print(f"⚠️ Arquivo de vídeo fonte não encontrado: {full_source_video_path}")
        return

    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir) # Remove diretório temporário antigo
    os.makedirs(temp_dir, exist_ok=True)

    scene_clip_paths = []
    total_main_clips_duration_sec = 0.0 # Para controlar o drawtext

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
        target_frame_number_str = scene.get("frame")
        target_scene_cuted_number = scene.get("scene_cuted")

        # Verifica se temos informações de áudio e pelo menos uma fonte visual (frame ou cena cortada)
        if not (audio_start_str and audio_end_str and (target_frame_number_str or target_scene_cuted_number)):
            print(f"⚠️ Dados incompletos para a cena {i+1} (áudio ou fonte visual ausente). Pulando.")
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

        cmd_video_scene = None
        if target_scene_cuted_number:
            if all_detected_scenes_data is None: # Carrega apenas uma vez
                path_cenas_detectadas_json = os.path.join(videos_baixados_dir, "cenas_detectadas.json")
                if os.path.exists(path_cenas_detectadas_json):
                    try:
                        with open(path_cenas_detectadas_json, "r", encoding='utf-8') as f_s:
                            all_detected_scenes_data = json.load(f_s)
                    except json.JSONDecodeError:
                        print(f"⚠️ Erro ao decodificar 'cenas_detectadas.json'. Não é possível usar cenas cortadas.")
                        all_detected_scenes_data = [] # Marca como problemático
                else:
                    print(f"⚠️ Arquivo 'cenas_detectadas.json' não encontrado. Não é possível usar cenas cortadas.")
                    all_detected_scenes_data = [] # Marca como não encontrado
            
            detected_scene_info = None
            if isinstance(all_detected_scenes_data, list):
                for det_scene in all_detected_scenes_data:
                    if det_scene.get("cena_numero") == target_scene_cuted_number:
                        detected_scene_info = det_scene
                        break
            
            if detected_scene_info and 'inicio_segundos' in detected_scene_info:
                video_cut_start_sec = detected_scene_info['inicio_segundos']
                cmd_video_scene = [
                    "ffmpeg", "-y",
                    "-ss", str(video_cut_start_sec),      # Ponto de início no vídeo fonte
                    "-i", full_source_video_path,         # Vídeo fonte original
                    "-i", temp_audio_clip_path,           # Áudio já cortado para esta cena
                    "-t", str(audio_duration_sec),        # Duração do clipe final (igual ao áudio)
                    "-map", "0:v:0",                      # Mapeia vídeo do primeiro input (vídeo fonte)
                    "-map", "1:a:0",                      # Mapeia áudio do segundo input (áudio cortado)
                    "-c:v", "libx264",                    # Re-encoder vídeo
                    "-c:a", "copy",                       # Copia o áudio (já está em AAC)
                    "-pix_fmt", "yuv420p",
                    "-shortest",                          # Garante que o clipe não seja maior que a entrada mais curta
                    temp_video_clip_path
                ]
            else:
                print(f"⚠️ Informações para 'scene_cuted' {target_scene_cuted_number} não encontradas em 'cenas_detectadas.json' ou formato inválido. Pulando cena {i+1}.")
                continue

        elif target_frame_number_str:
            if not os.path.exists(full_video_frames_dir):
                 print(f"⚠️ Diretório de frames '{full_video_frames_dir}' não encontrado, necessário para usar 'frame'. Pulando cena {i+1}.")
                 continue
            frame_image_path = find_frame_by_number(full_video_frames_dir, target_frame_number_str)
            if not frame_image_path:
                print(f"⚠️ Não foi possível encontrar o frame '{target_frame_number_str}' para a cena {i+1}. Pulando.")
                continue
            cmd_video_scene = [
                "ffmpeg", "-y", "-loop", "1", "-framerate", str(video_fps_output), "-i", frame_image_path,
                "-i", temp_audio_clip_path,
                "-c:v", "libx264", "-tune", "stillimage", "-c:a", "copy",
                "-pix_fmt", "yuv420p", "-t", str(audio_duration_sec), "-shortest",
                temp_video_clip_path
            ]

        if not cmd_video_scene: # Se nenhuma fonte visual foi processada
            print(f"⚠️ Não foi possível determinar o comando de vídeo para a cena {i+1}. Pulando.")
            continue

        # print(f"    Criando clipe da cena: {' '.join(cmd_video_scene)}") # Opcional: remover para limpar o output
        video_scene_process_result = subprocess.run(cmd_video_scene, capture_output=True, text=True)
        if video_scene_process_result.returncode != 0:
            print(f"⚠️ Erro ao criar clipe da cena {i+1}:")
            print(f"   Comando: {' '.join(cmd_video_scene)}")
            print(f"   ffmpeg stdout: {video_scene_process_result.stdout}")
            print(f"   ffmpeg stderr: {video_scene_process_result.stderr}")
            continue # Pula para a próxima cena
        scene_clip_paths.append(temp_video_clip_path)
        total_main_clips_duration_sec += audio_duration_sec # Acumula a duração dos clipes principais

    print(flush=True) # Nova linha após a barra de progresso concluir e garantir flush
    if not scene_clip_paths:
        print("⚠️ Nenhuma cena foi processada. Edição final não será criada.")
        shutil.rmtree(temp_dir)
        return # Sai da função se não há clipes para processar

    # --- Preparar clipe de Ebook (gerar se não existir) e lista de arquivos para concatenação ---
    ebook_dir = "ebook"  # Nova pasta para os arquivos fonte do ebook
    ebook_source_image = os.path.join(ebook_dir, "ebook.png")
    ebook_source_audio = os.path.join(ebook_dir, "ebook.mp3")

    temp_ebook_clip_filename = "ebook_clip.mp4" # Nome do arquivo do clipe do ebook na pasta temp
    temp_ebook_clip_path = os.path.join(temp_dir, temp_ebook_clip_filename) # Caminho completo na pasta temp

    path_for_ebook_in_filelist = None

    # Gerar clipe de ebook sempre e salvar na pasta temporária
    if os.path.exists(ebook_source_image) and os.path.exists(ebook_source_audio):
        print(f"   ⚙️ Gerando clipe de ebook a partir de '{ebook_source_image}' e '{ebook_source_audio}' para '{temp_ebook_clip_path}'...")
        duration_sec = get_audio_duration(ebook_source_audio)
        if duration_sec and duration_sec > 0:
            cmd_create_ebook = [
                "ffmpeg", "-y",
                "-loop", "1", "-framerate", str(video_fps_output), "-i", ebook_source_image,
                "-i", ebook_source_audio,
                "-map", "0:v:0", # Mapeia vídeo do primeiro input (imagem)
                "-map", "1:a:0", # Mapeia áudio do segundo input (arquivo de áudio)
                "-c:v", "libx264", # Mantém a remoção de -tune stillimage para robustez
                "-r", str(video_fps_output), # Define explicitamente o FPS do vídeo de saída
                # Pré-formata o clipe do ebook para o aspect ratio e resolução de saída (1080x1920)
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1",
                "-c:a", "aac", "-b:a", "192k", # Garante áudio AAC
                "-pix_fmt", "yuv420p",
                "-t", str(duration_sec),
                temp_ebook_clip_path # Salva diretamente na pasta temporária
            ]
            ebook_create_result = subprocess.run(cmd_create_ebook, capture_output=True, text=True)
            if ebook_create_result.returncode == 0:
                if os.path.exists(temp_ebook_clip_path) and os.path.getsize(temp_ebook_clip_path) > 1024: # Ex: > 1KB
                    print(f"   ✅ Clipe de ebook gerado e salvo em: {temp_ebook_clip_path} (Tamanho: {os.path.getsize(temp_ebook_clip_path)} bytes)")
                    path_for_ebook_in_filelist = temp_ebook_clip_filename # Usar o nome do arquivo para filelist.txt
                else:
                    file_size = os.path.getsize(temp_ebook_clip_path) if os.path.exists(temp_ebook_clip_path) else 'Não existe ou 0'
                    print(f"   ⚠️ FFmpeg retornou sucesso para clipe de ebook, mas o arquivo '{temp_ebook_clip_path}' é inválido ou muito pequeno (Tamanho: {file_size} bytes).")
                    print(f"      Comando: {' '.join(cmd_create_ebook)}")
                    print(f"      ffmpeg stdout: {ebook_create_result.stdout}")
                    print(f"      ffmpeg stderr: {ebook_create_result.stderr}")
                    # path_for_ebook_in_filelist permanece None
            else:
                print(f"   ⚠️ Erro ao gerar clipe de ebook:")
                print(f"      Comando: {' '.join(cmd_create_ebook)}")
                print(f"      ffmpeg stdout: {ebook_create_result.stdout}")
                print(f"      ffmpeg stderr: {ebook_create_result.stderr}")
                # path_for_ebook_in_filelist permanece None
        else:
            print(f"   ⚠️ Não foi possível obter duração válida para '{ebook_source_audio}'. Clipe de ebook não será gerado.")
    else:
        print(f"   ⚠️ Arquivos fonte '{ebook_source_image}' ou '{ebook_source_audio}' não encontrados na pasta '{ebook_dir}'. Clipe de ebook não será gerado/usado.")

    # Obter configurações de qualidade de saída
    output_qualities = config.get("output_qualities", [])
    if not output_qualities:
        print("⚠️ Nenhuma configuração de qualidade de saída encontrada. Usando qualidade padrão (CRF 23).")
        output_qualities = [{"name": "default", "crf": 23}] # Fallback padrão

    print("\n✨ Iniciando concatenação e codificação final em diferentes qualidades...")
    for quality_preset in output_qualities:
        quality_name = quality_preset.get("name", "custom")
        crf_value = quality_preset.get("crf", 23) # Default CRF 23 se não especificado
        
        # Nome do arquivo de vídeo final para esta qualidade
        output_edit_filename_quality = f"edit_final_{quality_name}.mp4"
        # Nome do arquivo intermediário (apenas cenas, com texto)
        intermediate_scenes_clip_name = f"intermediate_scenes_{quality_name}.mp4" # Usado internamente
        intermediate_scenes_clip_path = os.path.join(temp_dir, intermediate_scenes_clip_name)
        # Prepara o nome do vídeo para o filtro drawtext
        # Tenta usar movie_name do config, senão usa o nome do arquivo de vídeo sem extensão
        custom_movie_name = config.get("movie_name", "")
        if custom_movie_name and custom_movie_name.strip():
            text_to_draw = custom_movie_name.strip()
        elif source_video_name:
            text_to_draw = os.path.splitext(source_video_name)[0]
        else:
            text_to_draw = "Video Editado"
        # Escapa aspas simples dentro do nome do arquivo para o filtro drawtext do ffmpeg
        escaped_text_to_draw = text_to_draw.replace("'", "'\\''")
        
        # --- Etapa 1: Concatenar clipes de cena e aplicar filtros (scale, pad, drawtext) ---
        print(f"\n  -> Etapa 1/2: Gerando clipe de cenas '{intermediate_scenes_clip_name}' (CRF: {crf_value})...")

        drawtext_filter_options = f"drawtext=" \
                                  f"text='{escaped_text_to_draw}':" \
                                  f"fontfile='Arial':" \
                                  f"x=(w-text_w)/2:" \
                                  f"y=120:" \
                                  f"fontsize=40:" \
                                  f"fontcolor=white:" \
                                  f"box=1:boxcolor=black@0.4:boxborderw=5:" \
                                  f"enable='1'" # Habilita texto para toda a duração deste clipe de cenas

        vf_after_concat = f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,{drawtext_filter_options}"

        cmd_create_intermediate_scenes = ["ffmpeg", "-y"]
        for clip_path in scene_clip_paths: # scene_clip_paths contém caminhos completos
            cmd_create_intermediate_scenes.extend(["-i", clip_path])

        if len(scene_clip_paths) == 1:
            cmd_create_intermediate_scenes.extend([
                "-vf", vf_after_concat,
                "-c:v", "libx264", "-crf", str(crf_value),
                "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p", "-aspect", "9:16",
                intermediate_scenes_clip_path
            ])
        else: # Múltiplos clipes de cena, usar filtro concat
            filter_complex_str_scenes = ""
            for i_scene in range(len(scene_clip_paths)):
                filter_complex_str_scenes += f"[{i_scene}:v:0][{i_scene}:a:0]"
            filter_complex_str_scenes += f"concat=n={len(scene_clip_paths)}:v=1:a=1[concat_v][concat_a];"
            filter_complex_str_scenes += f"[concat_v]{vf_after_concat}[final_v]"

            cmd_create_intermediate_scenes.extend([
                "-filter_complex", filter_complex_str_scenes,
                "-map", "[final_v]",
                "-map", "[concat_a]",
                "-c:v", "libx264", "-crf", str(crf_value),
                "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p", "-aspect", "9:16",
                intermediate_scenes_clip_path
            ])
        intermediate_scenes_result = subprocess.run(cmd_create_intermediate_scenes, capture_output=True, text=True)
        if intermediate_scenes_result.returncode != 0:
            print(f"  ⚠️ Erro ao criar clipe de cenas intermediário '{intermediate_scenes_clip_name}':")
            print(f"     Comando: {' '.join(cmd_create_intermediate_scenes)}")
            print(f"     ffmpeg stdout: {intermediate_scenes_result.stdout}")
            print(f"     ffmpeg stderr: {intermediate_scenes_result.stderr}")
            continue # Pula para a próxima qualidade se esta falhar
        
        print(f"  ✅ Clipe de cenas intermediário '{intermediate_scenes_clip_name}' criado.")

        # --- Etapa 2: Concatenar clipe de cenas com clipe de ebook (se existir) ---
        print(f"  -> Etapa 2/2: Gerando edição final '{output_edit_filename_quality}'...")
        
        cmd_final_concat = ["ffmpeg", "-y"]
        input_files_for_final_concat = [intermediate_scenes_clip_path] # Caminho completo

        # path_for_ebook_in_filelist é o nome do arquivo (ex: "ebook_clip.mp4") se gerado com sucesso
        # temp_ebook_clip_path é o caminho completo para o clipe do ebook
        if path_for_ebook_in_filelist and os.path.exists(temp_ebook_clip_path):
            input_files_for_final_concat.append(temp_ebook_clip_path)
        elif path_for_ebook_in_filelist: # Foi marcado como gerado, mas não existe
            print(f"  ⚠️ Clipe de ebook '{temp_ebook_clip_filename}' foi marcado como gerado, mas não encontrado em '{temp_ebook_clip_path}'. Será omitido.")

        for input_file in input_files_for_final_concat:
            cmd_final_concat.extend(["-i", input_file])

        if len(input_files_for_final_concat) == 1:
            # Apenas o clipe de cenas intermediário, sem ebook.
            # Re-encoda para garantir CRF e formato de áudio final.
            cmd_final_concat.extend([
                "-c:v", "libx264", "-crf", str(crf_value),
                "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p", "-aspect", "9:16",
                output_edit_filename_quality
            ])
        else: # 2 inputs (cenas + ebook)
            filter_complex_final_str = ""
            for i_final in range(len(input_files_for_final_concat)):
                filter_complex_final_str += f"[{i_final}:v:0][{i_final}:a:0]"
            filter_complex_final_str += f"concat=n={len(input_files_for_final_concat)}:v=1:a=1[outv][outa]"
            
            cmd_final_concat.extend([
                "-filter_complex", filter_complex_final_str,
                "-map", "[outv]",
                "-map", "[outa]",
                "-c:v", "libx264", "-crf", str(crf_value),
                "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p", "-aspect", "9:16",
                output_edit_filename_quality
            ])

        final_concat_result = subprocess.run(cmd_final_concat, capture_output=True, text=True)
        if final_concat_result.returncode == 0:
            print(f"  ✅ Edição final '{output_edit_filename_quality}' criada com sucesso!")
        else:
            print(f"  ⚠️ Erro ao criar edição final '{output_edit_filename_quality}':")
            # Imprimir o comando pode ser útil para depuração
            print(f"     Comando: {' '.join(cmd_final_concat)}")
            print(f"     ffmpeg stdout: {final_concat_result.stdout}")
            print(f"     ffmpeg stderr: {final_concat_result.stderr}")

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
            "min_scene_duration_seconds": 2.0, # Valor padrão
            "use_scenes": False # Novo campo, padrão para False
        },
        "detectar_cortes_de_cena_video": { # Nova seção de configuração
            "enabled": True,
            "video_source_index": 0, # Índice do vídeo na links.txt para analisar (0 para o primeiro)
            "threshold": 27.0
        },
        "output_qualities": [ # Nova seção para qualidades de saída
            {
                "name": "low",
                "crf": 28
            },
            {
                "name": "medium",
                "crf": 24
            },
            {
                "name": "high",
                "crf": 20
            }
        ],
        "movie_name": "" # Novo campo para nome personalizado do filme
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
                    config_padrao["generate_edit_from_beats"] = {"enabled": config_padrao["generate_edit_from_beats"], "min_scene_duration_seconds": 2.0, "use_scenes": False}
                elif not isinstance(config_padrao.get("generate_edit_from_beats"), dict): # Se não for bool nem dict, reseta
                    config_padrao["generate_edit_from_beats"] = {"enabled": False, "min_scene_duration_seconds": 2.0, "use_scenes": False}
                else: # Garante que a nova chave use_scenes exista se generate_edit_from_beats for um dict
                    if "use_scenes" not in config_padrao["generate_edit_from_beats"]:
                        config_padrao["generate_edit_from_beats"]["use_scenes"] = False


                # Handle potential old boolean format for filtrar_batidas_por_amplitude (if it ever existed as bool)
                if isinstance(config_padrao.get("filtrar_batidas_por_amplitude"), bool):
                     config_padrao["filtrar_batidas_por_amplitude"] = {"enabled": config_padrao["filtrar_batidas_por_amplitude"], "min_amplitude_percentage": 75}
                elif not isinstance(config_padrao.get("filtrar_batidas_por_amplitude"), dict):
                     config_padrao["filtrar_batidas_por_amplitude"] = {"enabled": True, "min_amplitude_percentage": 75}
                
                # Garante que a subestrutura de detectar_cortes_de_cena_video exista
                if not isinstance(config_padrao.get("detectar_cortes_de_cena_video"), dict):
                    config_padrao["detectar_cortes_de_cena_video"] = {"enabled": True, "video_source_index": 0, "threshold": 27.0}
                    
                # Garante que a subestrutura de output_qualities exista e seja uma lista
                if not isinstance(config_padrao.get("output_qualities"), list):
                    config_padrao["output_qualities"] = [{"name": "default", "crf": 23}] # Reseta para padrão se não for lista
                
                if "movie_name" not in config_padrao: # Garante que a chave movie_name exista
                    config_padrao["movie_name"] = ""


                print(f"⚙️ Configurações carregadas de '{caminho_arquivo_config}'.")
                return config_padrao
        except json.JSONDecodeError as e:
            print(f"⚠️ Erro ao decodificar '{caminho_arquivo_config}': {e}. Usando configurações padrão.")
        except Exception as e:
            print(f"⚠️ Erro ao ler '{caminho_arquivo_config}': {e}. Usando configurações padrão.")
    else:
        print(f"ℹ️ Arquivo de configuração '{caminho_arquivo_config}' não encontrado. Usando configurações padrão.")
    return config_padrao

def gerar_edit_json_pelas_batidas(
    caminho_arquivo_batidas,
    pasta_frames_video_fonte, # Usado se use_scenes for false
    nome_video_fonte_no_json,
    nome_audio_fonte_no_json,
    generate_edit_config, # Contém min_scene_duration_seconds e use_scenes
    pasta_videos_baixados, # Para localizar cenas_detectadas.json
    caminho_saida_edit_json="edit.json"
    ):
    """
    Gera um arquivo edit.json usando os tempos de um arquivo de batidas e frames aleatórios.
    """
    print(f"\n🔄 Gerando '{caminho_saida_edit_json}' a partir de batidas e frames aleatórios...")
    if not caminho_arquivo_batidas or not os.path.exists(caminho_arquivo_batidas):
        print(f"⚠️ Arquivo de batidas não encontrado: {caminho_arquivo_batidas}")
        return False
    if not os.path.exists(pasta_frames_video_fonte):
        print(f"⚠️ Pasta de frames do vídeo fonte não encontrada: {pasta_frames_video_fonte}")
        return False

    try:
        min_duration_sec = generate_edit_config.get("min_scene_duration_seconds", 2.0)
        use_scenes_from_detection = generate_edit_config.get("use_scenes", False)

        with open(caminho_arquivo_batidas, "r", encoding='utf-8') as f:
            beat_timestamps_hhmmssff = [line.strip() for line in f if line.strip()]

        if len(beat_timestamps_hhmmssff) < 2:
            print(f"⚠️ Não há batidas suficientes em '{caminho_arquivo_batidas}' para criar cenas (necessário >= 2).")
            return False

        available_frame_numbers = []
        detected_scenes_data = []

        if use_scenes_from_detection:
            path_cenas_detectadas = os.path.join(pasta_videos_baixados, "cenas_detectadas.json")
            if os.path.exists(path_cenas_detectadas):
                with open(path_cenas_detectadas, "r", encoding='utf-8') as f_scenes:
                    detected_scenes_data = json.load(f_scenes)
                if not detected_scenes_data:
                    print(f"⚠️ Arquivo 'cenas_detectadas.json' está vazio. Não é possível usar cenas detectadas.")
                    use_scenes_from_detection = False # Fallback para frames se o arquivo estiver vazio
                else:
                    print(f"   Usando cenas do arquivo: {path_cenas_detectadas}")
            else:
                print(f"⚠️ Arquivo 'cenas_detectadas.json' não encontrado em '{pasta_videos_baixados}'. Não é possível usar cenas detectadas.")
                use_scenes_from_detection = False # Fallback para frames

        if not use_scenes_from_detection: # Se use_scenes for false ou fallback
            print(f"   Usando frames aleatórios de: {pasta_frames_video_fonte}")
            available_frames_files = [f for f in os.listdir(pasta_frames_video_fonte) if f.startswith("frame_") and f.lower().endswith(".jpg")]
            if not available_frames_files:
                print(f"⚠️ Nenhum arquivo de frame encontrado em '{pasta_frames_video_fonte}'.")
                return False
            for frame_file in available_frames_files:
                try:
                    parts = frame_file.split('_')
                    if len(parts) > 1 and parts[0] == "frame":
                        frame_num_str = str(int(parts[1]))
                        available_frame_numbers.append(frame_num_str)
                except (ValueError, IndexError):
                    print(f"   Aviso: Não foi possível extrair o número do frame de '{frame_file}'. Pulando.")
            if not available_frame_numbers:
                print(f"⚠️ Nenhum número de frame válido pôde ser extraído dos arquivos em '{pasta_frames_video_fonte}'.")
                return False




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
                scene_entry = {"audio_start": audio_start_str, "audio_end": suitable_audio_end_str}
                added_scene_content = False

                if use_scenes_from_detection and detected_scenes_data:
                    current_audio_duration = parse_hhmmssff_to_seconds(suitable_audio_end_str, fps_for_parsing) - parse_hhmmssff_to_seconds(audio_start_str, fps_for_parsing)
                    candidate_detected_scenes = [
                        s for s in detected_scenes_data 
                        if (s['fim_segundos'] - s['inicio_segundos']) >= current_audio_duration
                    ]
                    if candidate_detected_scenes:
                        chosen_detected_scene = random.choice(candidate_detected_scenes)
                        scene_entry["scene_cuted"] = chosen_detected_scene["cena_numero"]
                        added_scene_content = True
                    else:
                        print(f"   ℹ️ Nenhuma cena detectada com duração >= ao áudio ({current_audio_duration:.2f}s) para {audio_start_str} - {suitable_audio_end_str}. Usando fallback de cena aleatória.")
                        if len(detected_scenes_data) >= 3:
                            # Exclui a primeira e a última para a escolha aleatória
                            fallback_candidate_pool = detected_scenes_data[1:-1]
                            chosen_detected_scene = random.choice(fallback_candidate_pool)
                            scene_entry["scene_cuted"] = chosen_detected_scene["cena_numero"]
                            added_scene_content = True
                            print(f"     Fallback: Usando início da cena detectada nº {chosen_detected_scene['cena_numero']} (de {len(fallback_candidate_pool)} internas) com duração do áudio.")
                        elif detected_scenes_data: # Se 1 ou 2 cenas detectadas, escolhe qualquer uma
                            chosen_detected_scene = random.choice(detected_scenes_data)
                            scene_entry["scene_cuted"] = chosen_detected_scene["cena_numero"]
                            added_scene_content = True
                            print(f"     Fallback: Usando início da cena detectada nº {chosen_detected_scene['cena_numero']} (de {len(detected_scenes_data)} disponíveis) com duração do áudio.")
                        else:
                            # Este caso não deve ser alcançado se detected_scenes_data foi verificado como não vazio antes.
                            print(f"     Fallback falhou: Nenhuma cena detectada disponível.")
                
                elif not use_scenes_from_detection and available_frame_numbers: # Fallback ou modo frame
                    selected_frame_number = random.choice(available_frame_numbers)
                    scene_entry["frame"] = selected_frame_number
                    added_scene_content = True

                if added_scene_content:
                    scenes.append(scene_entry)
                
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
            # Importar aqui para evitar dependência se não for usado
            from audio_processing import baixar_audio_youtube as download_audio_func
            caminho_do_arquivo_de_musica, _ = download_audio_func(youtube_url_musica, songs_directory)
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

    # --- 4.1. Detecção de Cortes de Cena no Vídeo (se habilitado) ---
    scene_detection_config = config.get("detectar_cortes_de_cena_video", {})
    if isinstance(scene_detection_config, dict) and scene_detection_config.get("enabled"):
        print("\n⚙️ Tentando detectar cortes de cena no vídeo...")
        video_idx_to_analyze = scene_detection_config.get("video_source_index", 0)
        detection_threshold = scene_detection_config.get("threshold", 27.0)
        
        video_para_analise_de_cena = None
        
        if os.path.exists(arquivo_links):
            with open(arquivo_links, "r", encoding='utf-8') as f_links_sd:
                links_videos_sd = [linha.strip() for linha in f_links_sd if linha.strip() and not linha.startswith("#")]
            
            if 0 <= video_idx_to_analyze < len(links_videos_sd):
                url_video_para_cena = links_videos_sd[video_idx_to_analyze]
                # Tenta localizar o vídeo baixado correspondente a esta URL
                caminho_video_esperado_para_cena = resolver_nome_arquivo_yt_dlp(url_video_para_cena, pasta_destino_videos, extrair_audio=False)
                if caminho_video_esperado_para_cena and os.path.exists(caminho_video_esperado_para_cena):
                    video_para_analise_de_cena = caminho_video_esperado_para_cena
                else:
                    print(f"   ⚠️ Vídeo para análise de cena (índice {video_idx_to_analyze} de links.txt) não encontrado em '{pasta_destino_videos}'.")
                    if caminho_video_esperado_para_cena:
                         print(f"      Caminho esperado: {caminho_video_esperado_para_cena}")
            else:
                print(f"   ⚠️ Índice de vídeo para análise de cena ({video_idx_to_analyze}) fora do intervalo de links em '{arquivo_links}'.")
        else:
            print(f"   ⚠️ Arquivo de links '{arquivo_links}' não encontrado. Não é possível determinar o vídeo para análise de cena.")

        if video_para_analise_de_cena:
            output_json_scene_cuts = os.path.join(pasta_destino_videos, "cenas_detectadas.json") # Nome do arquivo de saída alterado
            detectar_cortes_de_cena(video_para_analise_de_cena, output_json_scene_cuts, threshold=detection_threshold)
        else:
            print("   ℹ️ Detecção de cortes de cena pulada: vídeo fonte não pôde ser determinado ou encontrado.")
    else:
        print("\nℹ️ Detecção de cortes de cena no vídeo desabilitada nas configurações.")

    # --- 5. Gerar edit.json a partir das batidas (se habilitado) ---
    generate_edit_config = config.get("generate_edit_from_beats", {})
    if isinstance(generate_edit_config, dict) and generate_edit_config.get("enabled"):
        print("\n⚙️ Tentando gerar 'edit.json' a partir de arquivos existentes (batidas e frames)...")

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
                 generate_edit_config, # Passa todo o sub-dicionário de config
                 pasta_destino_videos, # Para localizar cenas_detectadas.json
                 edit_json_file # Nome do arquivo de saída
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
                criar_edite_do_json(conteudo_edit, config) # Passa o dicionário config
            except json.JSONDecodeError as e:
                print(f"⚠️ Erro ao decodificar '{edit_json_file}': {e}. Não será possível criar o edit.")
            except Exception as e:
                import traceback
                print(f"⚠️ Erro ao processar '{edit_json_file}' para criação do edit: {e}")
                print("Detalhes do erro:")
                traceback.print_exc()

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
