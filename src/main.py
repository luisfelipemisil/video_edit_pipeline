# -*- coding: utf-8 -*-
import os
import subprocess
import time
# import cv2 # Movido para video_processing se necessário lá
from dotenv import load_dotenv
import json
# import shutil # Movido para editing ou utils
# import random # Movido para editing
import platform
import sys

from .audio_processing import ( 
    analisar_batidas_audio,
    load_amplitude_data,
    filter_timestamps_by_amplitude
)
from .video_processing import ( 
    extrair_frames,
    detectar_cortes_de_cena 
)
from .utils import (
    resolver_nome_arquivo_yt_dlp, 
    format_seconds_to_hhmmssff,
    comment_line_in_file, # Movido para utils
    # parse_hhmmssff_to_seconds, # Usado em editing.py, importado lá
    # find_frame_by_number, # Usado em editing.py, importado lá
    get_audio_duration
)
from .downloading import baixar_video, baixar_audio_youtube
from .editing import criar_edite_do_json, gerar_edit_json_pelas_batidas
from .config_loader import carregar_configuracao

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Define o diretório base do projeto (um nível acima de src)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        pass
except Exception as e:
    pass

# Exemplo de uso
if __name__ == "__main__":
    edit_json_file = os.path.join(BASE_DIR, "src", "config", "edit.json")        # Ajustado
    config_geral_file = os.path.join(BASE_DIR, "src", "config", "config.json")  # Ajustado

    # Carrega as configurações gerais
    config = carregar_configuracao(config_geral_file)
    print(f"Configurações de execução: {config}")

    arquivo_links = os.path.join(BASE_DIR, "src", "data", "links.txt")          # Ajustado
    pasta_destino_videos = os.path.join(BASE_DIR, "videos_baixados")
    intervalo_para_frames_seg = 1 # Extrair um frame a cada X segundos
    qualidade_dos_frames_jpeg = 75 # Qualidade JPEG (0-100), menor valor = menor tamanho/qualidade
    songs_directory = os.path.join(BASE_DIR, "songs")
    musica_config_file = os.path.join(BASE_DIR, "src", "data", "musica.txt")    # Ajustado

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
            download_audio_func = baixar_audio_youtube # Já importado de .downloading
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

    # --- 2.5 Preparar Áudio para Análise de Batidas (Truncamento Opcional) ---
    # caminho_audio_para_analise será o arquivo efetivamente usado pela função de análise de batidas.
    # Pode ser o original ou uma versão truncada.
    caminho_audio_para_analise = None 

    if caminho_do_arquivo_de_musica: # Se um áudio foi definido via musica.txt
        caminho_audio_para_analise = caminho_do_arquivo_de_musica # Padrão: usar o original
        
        max_music_duration_sec = config.get("max_music_duration_seconds", 0.0)
        # Garante que é um número float válido para a comparação
        if not isinstance(max_music_duration_sec, (int, float)):
            max_music_duration_sec = 0.0
        print(f"   Configuração 'max_music_duration_seconds': {max_music_duration_sec}s")

        if max_music_duration_sec > 0:
            print(f"\n⚙️ Verificando necessidade de truncar áudio '{os.path.basename(caminho_do_arquivo_de_musica)}' para análise (limite: {max_music_duration_sec}s)...")
            original_duration = get_audio_duration(caminho_do_arquivo_de_musica) 
            print(f"   Duração original detectada para '{os.path.basename(caminho_do_arquivo_de_musica)}': {original_duration}s")

            if original_duration is not None:
                if original_duration > max_music_duration_sec:
                    # O arquivo original será substituído.
                    # Criar um nome de arquivo temporário para a saída do ffmpeg.
                    # Este arquivo temporário será criado no mesmo diretório do original.
                    original_dir = os.path.dirname(caminho_do_arquivo_de_musica)
                    original_basename, original_ext = os.path.splitext(os.path.basename(caminho_do_arquivo_de_musica))
                    temp_output_audio_path = os.path.join(original_dir, f"{original_basename}.trunc_temp{original_ext}")

                    print(f"   Truncando '{os.path.basename(caminho_do_arquivo_de_musica)}' (duração: {original_duration:.2f}s) para {max_music_duration_sec:.2f}s.")
                    print(f"   ℹ️ O arquivo original '{os.path.basename(caminho_do_arquivo_de_musica)}' será substituído se o truncamento for bem-sucedido.")
                    cmd_truncate = [ # Comando para truncar
                        "ffmpeg", "-y",
                        "-i", caminho_do_arquivo_de_musica,
                        "-ss", "0", 
                        "-t", str(max_music_duration_sec),
                        "-vn", # Sem vídeo
                        "-c:a", "copy", # Copia o codec de áudio se possível (yt-dlp geralmente baixa mp3)
                        temp_output_audio_path # Saída para o arquivo temporário
                    ]
                    
                    truncate_result = subprocess.run(cmd_truncate, capture_output=True, text=True, check=False, encoding='utf-8')

                    if truncate_result.returncode == 0 and os.path.exists(temp_output_audio_path):
                        try:
                            # Tenta remover o original antes de renomear o temporário
                            if os.path.exists(caminho_do_arquivo_de_musica): # Deveria sempre existir aqui
                                os.remove(caminho_do_arquivo_de_musica)
                            os.rename(temp_output_audio_path, caminho_do_arquivo_de_musica)
                            print(f"   ✅ Áudio original '{os.path.basename(caminho_do_arquivo_de_musica)}' foi substituído pela versão truncada.")
                            caminho_audio_para_analise = caminho_do_arquivo_de_musica # Usar o arquivo original (agora truncado)
                            print(f"   Áudio para análise agora é: {caminho_audio_para_analise} (truncado)")
                            # caminho_do_arquivo_de_musica já aponta para o arquivo correto (que agora está truncado)
                            # A mensagem "será usado para a edição final" já está implícita.
                        except OSError as e:
                            print(f"   ⚠️ Falha ao substituir o arquivo original '{os.path.basename(caminho_do_arquivo_de_musica)}' pelo truncado: {e}")
                            print(f"      A versão truncada pode estar em: {temp_output_audio_path}")
                            print(f"      A análise de batidas e a edição usarão o áudio original não truncado.")
                            # caminho_audio_para_analise permanece como o original não truncado, que não foi alterado.
                            # Se o rename falhar, caminho_do_arquivo_de_musica ainda é o original não truncado.
                    else:
                        print(f"   ⚠️ Falha ao criar a versão truncada temporária do áudio. O arquivo original não foi modificado.")
                        print(f"      Comando: {' '.join(cmd_truncate)}")
                        if truncate_result.stderr: print(f"      Stderr: {truncate_result.stderr.strip()}")
                        if os.path.exists(temp_output_audio_path): # Limpa o temporário se ffmpeg falhou mas o arquivo foi criado
                            try: os.remove(temp_output_audio_path)
                            except OSError: pass
                        # caminho_audio_para_analise permanece como o original não truncado
                else:
                    print(f"   Áudio original ({original_duration:.2f}s) já está dentro do limite de {max_music_duration_sec}s. Não é necessário truncar.")
                    # caminho_audio_para_analise já é caminho_do_arquivo_de_musica (original)
            else:
                print(f"   ⚠️ Não foi possível obter a duração do áudio original '{os.path.basename(caminho_do_arquivo_de_musica)}'. Não será truncado para análise.")
                # caminho_audio_para_analise já é caminho_do_arquivo_de_musica (original)

    # --- 3. Análise de Batidas (se habilitada e áudio disponível) ---
    if config.get("analisar_batidas_do_audio"):
        try:
            import librosa
            import numpy as np
            librosa_disponivel = True
        except ImportError:
            librosa_disponivel = False
            print("\n⚠️ Análise de batidas desabilitada: librosa ou numpy não está instalado.")
            print("   Por favor, instale com: pip install librosa numpy")

        if librosa_disponivel:
            # audio_para_analise foi definido na seção 2.5 (pode ser o original ou truncado)
            # ou ainda é None se caminho_do_arquivo_de_musica era None.
            audio_final_para_processar_batidas = caminho_audio_para_analise

            if not audio_final_para_processar_batidas: # Se musica.txt não forneceu um áudio válido
                print(f"\n🎵 'musica.txt' não forneceu áudio ou falhou o processamento inicial. Procurando áudio em '{songs_directory}' para análise...")
                # Fallback: Tenta encontrar um arquivo de áudio na pasta 'songs'
                if os.path.exists(songs_directory) and os.path.isdir(songs_directory):
                    audio_files = []
                    audio_extensions = ('.mp3', '.wav', '.aac', '.m4a', '.ogg', '.flac')
                    excluded_suffix = "_truncated_for_beats_analysis" # Para não pegar arquivos de análise como fallback principal
                    for f_name in os.listdir(songs_directory):
                        file_path = os.path.join(songs_directory, f_name)
                        if os.path.isfile(file_path) and \
                           f_name.lower().endswith(audio_extensions) and \
                           not f_name.endswith(excluded_suffix + os.path.splitext(f_name)[1]):
                            audio_files.append(file_path)
                    
                    if audio_files:
                        try:
                            latest_audio_file = max(audio_files, key=os.path.getmtime)
                            audio_final_para_processar_batidas = latest_audio_file
                            print(f"   🎵 Áudio mais recente (fallback) encontrado para análise de batidas: {audio_final_para_processar_batidas}")
                        except Exception as e:
                            print(f"   ⚠️ Erro ao determinar o áudio mais recente (fallback): {e}. Usando o primeiro encontrado alfabeticamente.")
                            audio_final_para_processar_batidas = sorted(audio_files)[0] if audio_files else None
                            if audio_final_para_processar_batidas:
                                 print(f"   🎵 Áudio (fallback alfabético) encontrado para análise de batidas: {audio_final_para_processar_batidas}")
            
            if audio_final_para_processar_batidas:
                print(f"\n🎵 Usando áudio para análise de batidas: {os.path.basename(audio_final_para_processar_batidas)}")
                fps_referencia_batidas = 25
                pasta_batidas_analisadas = os.path.join(songs_directory, "analise_batidas")
                arquivo_beats_processado, arquivo_beats_with_amplitude_processado = analisar_batidas_audio(
                    audio_final_para_processar_batidas, 
                    pasta_batidas_analisadas, 
                    fps_para_timestamp=fps_referencia_batidas
                )
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
        pasta_batidas_dir = os.path.join(songs_directory, "analise_batidas") # Corrigido para usar songs_directory
        # Agora buscamos especificamente por beats.txt, que é o arquivo potencialmente filtrado
        if os.path.exists(pasta_batidas_dir):
            caminho_beats_txt_esperado = os.path.join(pasta_batidas_dir, "beats.txt")
            if os.path.exists(caminho_beats_txt_esperado):
                 caminho_batidas_a_usar = caminho_beats_txt_esperado
                 print(f"   🎶 Usando arquivo de batidas: {caminho_batidas_a_usar}")
            else:
                print(f"   ⚠️ Arquivo de batidas '{caminho_beats_txt_esperado}' não encontrado.")
        else:
            print(f"   ⚠️ Pasta de análise de batidas '{pasta_batidas_dir}' não encontrada.")


        # B. Determinar nome do áudio para JSON a partir da pasta 'songs'
        # Priorizar o áudio original definido em musica.txt para o nome no JSON.
        # A variável `nome_audio_para_json` já existe no código original.
        if os.path.exists(songs_directory) and os.path.isdir(songs_directory):
            if caminho_do_arquivo_de_musica: # Se musica.txt definiu um áudio (este caminho é o do arquivo original, que pode ter sido truncado no local)
                # Gera o caminho relativo à pasta 'songs' para o edit.json
                # Ex: se caminho_do_arquivo_de_musica for "/abs/path/songs/minha_musica.mp3", e songs_directory for "/abs/path/songs", o relpath será "minha_musica.mp3".
                nome_audio_para_json = os.path.relpath(caminho_do_arquivo_de_musica, songs_directory)
                print(f"   🎵 Usando nome de áudio (de musica.txt) para JSON: {nome_audio_para_json}")
            else:
                # Fallback: encontrar o mais recente na pasta songs, excluindo os temporários de análise
                audio_extensions = ('.mp3', '.wav', '.aac', '.m4a', '.ogg', '.flac')
                song_files_for_json = []
                excluded_suffix_for_json = "_truncated_for_beats_analysis"
                for f_name in os.listdir(songs_directory):
                    file_path = os.path.join(songs_directory, f_name)
                    if os.path.isfile(file_path) and \
                       f_name.lower().endswith(audio_extensions) and \
                       not f_name.endswith(excluded_suffix_for_json + os.path.splitext(f_name)[1]):
                        song_files_for_json.append(f_name)
                
                if song_files_for_json:
                    try:
                        latest_song_file_name = max(song_files_for_json, key=lambda f: os.path.getmtime(os.path.join(songs_directory, f)))
                        nome_audio_para_json = latest_song_file_name
                        print(f"   🎵 Usando arquivo de áudio mais recente (fallback) em '{songs_directory}' para JSON: {nome_audio_para_json}")
                    except Exception as e:
                        print(f"   ⚠️ Erro ao determinar o áudio mais recente (fallback) para JSON: {e}. Usando o primeiro encontrado alfabeticamente.")
                        nome_audio_para_json = sorted(song_files_for_json)[0] if song_files_for_json else None
                        if nome_audio_para_json:
                            print(f"   🎵 Usando arquivo de áudio (fallback alfabético) em '{songs_directory}' para JSON: {nome_audio_para_json}")

        if not nome_audio_para_json: # Se ainda não foi definido
            print(f"   ⚠️ Nenhum arquivo de áudio ({', '.join(audio_extensions)}) encontrado em '{songs_directory}'.")

        # C. Determinar nome_video_para_json (vídeo mais recente em videos_baixados)
        if os.path.exists(pasta_destino_videos) and os.path.isdir(pasta_destino_videos):
            video_files_in_dest = []
            video_extensions = ('.mp4', '.webm', '.mkv', '.avi', '.mov')
            for f_name in os.listdir(pasta_destino_videos):
                if os.path.isfile(os.path.join(pasta_destino_videos, f_name)) and f_name.lower().endswith(video_extensions):
                    video_files_in_dest.append(os.path.join(pasta_destino_videos, f_name))
            
            if video_files_in_dest:
                try:
                    latest_video_file_path = max(video_files_in_dest, key=os.path.getmtime)
                    nome_video_para_json = os.path.basename(latest_video_file_path)
                    print(f"   🎞️ Usando vídeo baixado mais recente para JSON: {nome_video_para_json}")
                except Exception as e:
                    print(f"   ⚠️ Erro ao determinar o vídeo mais recente para JSON: {e}. Usando o primeiro encontrado alfabeticamente.")
                    if video_files_in_dest:
                        nome_video_para_json = os.path.basename(sorted(video_files_in_dest)[0])
                        print(f"   🎞️ Usando vídeo baixado (fallback) para JSON: {nome_video_para_json}")
        
        if not nome_video_para_json:
             print(f"   ⚠️ Nenhum arquivo de vídeo encontrado em '{pasta_destino_videos}' para usar no JSON.")

        # D. Determinar pasta_frames_a_usar SE generate_edit_config["use_scenes"] for False
        if nome_video_para_json and not generate_edit_config.get("use_scenes"):
            frames_dir_for_video = os.path.join(pasta_destino_videos, os.path.splitext(nome_video_para_json)[0] + "_frames")
            if os.path.exists(frames_dir_for_video) and os.path.isdir(frames_dir_for_video):
                if any(f.lower().endswith(".jpg") for f in os.listdir(frames_dir_for_video) if os.path.isfile(os.path.join(frames_dir_for_video, f))):
                    pasta_frames_a_usar = frames_dir_for_video
                    print(f"   🖼️ Usando pasta de frames '{pasta_frames_a_usar}' para o vídeo '{nome_video_para_json}'.")
                else:
                    print(f"   ⚠️ Pasta de frames '{frames_dir_for_video}' encontrada, mas está vazia ou não contém arquivos .jpg.")
            else:
                print(f"   ⚠️ Pasta de frames '{frames_dir_for_video}' não encontrada para o vídeo '{nome_video_para_json}'. A extração de frames pode estar desabilitada ou falhou.")
        elif generate_edit_config.get("use_scenes"):
            print(f"   ℹ️ Usando cenas detectadas. Pasta de frames não é estritamente necessária para gerar edit.json.")
            # pasta_frames_a_usar permanece None, o que é ok para gerar_edit_json_pelas_batidas se use_scenes=True

        # E. Gerar JSON se todos os componentes foram encontrados/determinados
        can_generate_edit_json = (
            caminho_batidas_a_usar and
            nome_video_para_json and
            nome_audio_para_json and
            (pasta_frames_a_usar if not generate_edit_config.get("use_scenes") else True) # pasta_frames é opcional se use_scenes=True
        )

        if can_generate_edit_json:
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


        if can_generate_edit_json and caminho_batidas_a_usar: # Re-check caminho_batidas_a_usar
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
            if not pasta_frames_a_usar and not generate_edit_config.get("use_scenes"):
                print("      - Pasta de frames não determinada/encontrada (necessária se não usar cenas detectadas).")
            if not nome_video_para_json: print("      - Nome do vídeo para JSON não determinado.")
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
                criar_edite_do_json(conteudo_edit, config, BASE_DIR) # Passa o dicionário config e BASE_DIR
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
