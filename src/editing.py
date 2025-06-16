# -*- coding: utf-8 -*-
import os
import subprocess
import json
import shutil
import random

from .utils import parse_hhmmssff_to_seconds, find_frame_by_number, get_audio_duration

def criar_edite_do_json(edit_data, config, base_dir):
    """
    Cria um vídeo editado com base nas especificações do arquivo JSON.
    """
    print("\n🎬 Iniciando criação do edit a partir de 'edit.json'...")

    videos_baixados_dir = os.path.join(base_dir, "videos_baixados")
    songs_dir = os.path.join(base_dir, "songs")
    temp_dir = os.path.join(base_dir, "temp_edit_files")
    ebook_dir = os.path.join(base_dir, "ebook") 

    video_fps_output = 25 

    source_video_name = edit_data.get("source_video")
    source_audio_name = edit_data.get("source_audio")
    scenes_data = edit_data.get("scenes", [])
    all_detected_scenes_data = None 

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
    if not os.path.exists(full_source_video_path):
        print(f"⚠️ Arquivo de vídeo fonte não encontrado: {full_source_video_path}")
        return

    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir) 
    os.makedirs(temp_dir, exist_ok=True)

    scene_clip_paths = []
    total_main_clips_duration_sec = 0.0

    total_scenes = len(scenes_data)
    print(f"  Total de cenas a processar: {total_scenes}")

    for i, scene in enumerate(scenes_data):
        progress = (i + 1) / total_scenes
        bar_length = 30
        filled_length = int(bar_length * progress)
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        print(f"\r  Processando cena {i+1}/{total_scenes} [{bar}] {progress*100:.1f}%", end="", flush=True)

        audio_start_str = scene.get("audio_start")
        audio_end_str = scene.get("audio_end")
        target_frame_number_str = scene.get("frame")
        target_scene_cuted_number = scene.get("scene_cuted")

        if not (audio_start_str and audio_end_str and (target_frame_number_str or target_scene_cuted_number)):
            print(f"⚠️ Dados incompletos para a cena {i+1} (áudio ou fonte visual ausente). Pulando.")
            continue

        try:
            audio_start_sec = parse_hhmmssff_to_seconds(audio_start_str, fps=video_fps_output)
            audio_end_sec = parse_hhmmssff_to_seconds(audio_end_str, fps=video_fps_output)
        except ValueError as e:
            print(f"⚠️ Erro ao converter timestamps para a cena {i+1}: {e}. Pulando.")
            continue

        audio_duration_sec = audio_end_sec - audio_start_sec
        if audio_duration_sec <= 0:
            print(f"⚠️ Duração do áudio inválida para a cena {i+1} ({audio_duration_sec}s). Pulando.")
            continue

        temp_audio_clip_path = os.path.join(temp_dir, f"scene_{i+1}_audio.aac")
        temp_video_clip_path = os.path.join(temp_dir, f"scene_{i+1}_video.mp4")

        cmd_audio = [
            "ffmpeg", "-y", "-i", full_audio_path,
            "-ss", str(audio_start_sec), "-t", str(audio_duration_sec),
            "-c:a", "aac", "-b:a", "192k", temp_audio_clip_path
        ]
        audio_process_result = subprocess.run(cmd_audio, capture_output=True, text=True)
        if audio_process_result.returncode != 0:
            print(f"⚠️ Erro ao cortar áudio para cena {i+1}:\n   {audio_process_result.stderr}")
            continue

        cmd_video_scene = None
        if target_scene_cuted_number:
            if all_detected_scenes_data is None:
                path_cenas_detectadas_json = os.path.join(videos_baixados_dir, "cenas_detectadas.json")
                if os.path.exists(path_cenas_detectadas_json):
                    try:
                        with open(path_cenas_detectadas_json, "r", encoding='utf-8') as f_s:
                            all_detected_scenes_data = json.load(f_s)
                    except json.JSONDecodeError:
                        all_detected_scenes_data = []
                else:
                    all_detected_scenes_data = []
            
            detected_scene_info = next((s for s in all_detected_scenes_data if s.get("cena_numero") == target_scene_cuted_number), None)
            
            if detected_scene_info and 'inicio_segundos' in detected_scene_info:
                video_cut_start_sec = detected_scene_info['inicio_segundos']
                cmd_video_scene = [
                    "ffmpeg", "-y", "-ss", str(video_cut_start_sec), "-i", full_source_video_path,
                    "-i", temp_audio_clip_path, "-t", str(audio_duration_sec),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-c:a", "copy",
                    "-pix_fmt", "yuv420p", "-shortest", temp_video_clip_path
                ]
            else:
                print(f"⚠️ Informações para 'scene_cuted' {target_scene_cuted_number} não encontradas. Pulando cena {i+1}.")
                continue

        elif target_frame_number_str:
            if not os.path.exists(full_video_frames_dir):
                 print(f"⚠️ Diretório de frames '{full_video_frames_dir}' não encontrado. Pulando cena {i+1}.")
                 continue
            frame_image_path = find_frame_by_number(full_video_frames_dir, target_frame_number_str)
            if not frame_image_path:
                print(f"⚠️ Frame '{target_frame_number_str}' não encontrado. Pulando cena {i+1}.")
                continue
            cmd_video_scene = [
                "ffmpeg", "-y", "-loop", "1", "-framerate", str(video_fps_output), "-i", frame_image_path,
                "-i", temp_audio_clip_path, "-c:v", "libx264", "-tune", "stillimage", "-c:a", "copy",
                "-pix_fmt", "yuv420p", "-t", str(audio_duration_sec), "-shortest", temp_video_clip_path
            ]

        if not cmd_video_scene:
            print(f"⚠️ Comando de vídeo não determinado para cena {i+1}. Pulando.")
            continue

        video_scene_process_result = subprocess.run(cmd_video_scene, capture_output=True, text=True)
        if video_scene_process_result.returncode != 0:
            print(f"⚠️ Erro ao criar clipe da cena {i+1}:\n   {video_scene_process_result.stderr}")
            # Adiciona um print do comando para depuração
            print(f"   Comando falho: {' '.join(cmd_video_scene)}")
            continue
        
        if os.path.exists(temp_video_clip_path) and os.path.getsize(temp_video_clip_path) > 1024: # Verifica se o arquivo existe e tem mais de 1KB
            scene_clip_paths.append(temp_video_clip_path)
            total_main_clips_duration_sec += audio_duration_sec
        else:
            print(f"⚠️ Clipe da cena {i+1} ('{temp_video_clip_path}') não foi gerado corretamente ou está vazio. Pulando.")

    print(flush=True)
    if not scene_clip_paths:
        print("⚠️ Nenhuma cena processada. Edição final não será criada.")
        shutil.rmtree(temp_dir)
        return

    ebook_source_image = os.path.join(ebook_dir, "ebook.png")
    ebook_source_audio = os.path.join(ebook_dir, "ebook.mp3")
    temp_ebook_clip_filename = "ebook_clip.mp4"
    temp_ebook_clip_path = os.path.join(temp_dir, temp_ebook_clip_filename)
    path_for_ebook_in_filelist = None

    if os.path.exists(ebook_source_image) and os.path.exists(ebook_source_audio):
        print(f"   ⚙️ Gerando clipe de ebook para '{temp_ebook_clip_path}'...")
        duration_sec = get_audio_duration(ebook_source_audio)
        if duration_sec and duration_sec > 0:
            cmd_create_ebook = [
                "ffmpeg", "-y", "-loop", "1", "-framerate", str(video_fps_output), "-i", ebook_source_image,
                "-i", ebook_source_audio, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264",
                "-r", str(video_fps_output), 
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1",
                "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-t", str(duration_sec),
                temp_ebook_clip_path
            ]
            ebook_create_result = subprocess.run(cmd_create_ebook, capture_output=True, text=True)
            if ebook_create_result.returncode == 0 and os.path.exists(temp_ebook_clip_path) and os.path.getsize(temp_ebook_clip_path) > 1024:
                print(f"   ✅ Clipe de ebook gerado: {temp_ebook_clip_path}")
                path_for_ebook_in_filelist = temp_ebook_clip_filename
            else:
                print(f"   ⚠️ Erro ao gerar clipe de ebook ou arquivo inválido:\n     {ebook_create_result.stderr}")
        else:
            print(f"   ⚠️ Duração inválida para '{ebook_source_audio}'. Clipe de ebook não gerado.")
    else:
        print(f"   ⚠️ Arquivos fonte para ebook não encontrados. Clipe de ebook não gerado.")

    output_qualities = config.get("output_qualities", [{"name": "default", "crf": 23}])
    print("\n✨ Iniciando concatenação e codificação final...")

    for quality_preset in output_qualities:
        quality_name = quality_preset.get("name", "custom")
        crf_value = quality_preset.get("crf", 23)
        
        output_edit_filename_quality = os.path.join(base_dir, f"edit_final_{quality_name}.mp4")
        intermediate_scenes_clip_name = f"intermediate_scenes_{quality_name}.mp4"
        intermediate_scenes_clip_path = os.path.join(temp_dir, intermediate_scenes_clip_name)
        
        custom_movie_name = config.get("movie_name", "")
        text_to_draw = custom_movie_name.strip() or os.path.splitext(source_video_name)[0]
        escaped_text_to_draw = text_to_draw.replace("'", "'\\''")
        
        print(f"\n  -> Etapa 1/2: Gerando clipe de cenas '{intermediate_scenes_clip_name}' (CRF: {crf_value})...")
        drawtext_filter = f"drawtext=text='{escaped_text_to_draw}':fontfile='Arial':x=(w-text_w)/2:y=576:fontsize=40:fontcolor=white:box=1:boxcolor=black@0.4:boxborderw=5:enable='1'"
        vf_after_concat = f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,{drawtext_filter}"

        cmd_create_intermediate_scenes = ["ffmpeg", "-y"]
        for clip_path in scene_clip_paths:
            cmd_create_intermediate_scenes.extend(["-i", clip_path])

        if len(scene_clip_paths) == 1:
            cmd_create_intermediate_scenes.extend([
                "-vf", vf_after_concat, "-c:v", "libx264", "-crf", str(crf_value),
                "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-aspect", "9:16",
                intermediate_scenes_clip_path
            ])
        else:
            filter_complex_str_scenes = "".join([f"[{i_scene}:v:0][{i_scene}:a:0]" for i_scene in range(len(scene_clip_paths))])
            filter_complex_str_scenes += f"concat=n={len(scene_clip_paths)}:v=1:a=1[concat_v][concat_a];"
            filter_complex_str_scenes += f"[concat_v]{vf_after_concat}[final_v]"
            cmd_create_intermediate_scenes.extend([
                "-filter_complex", filter_complex_str_scenes, "-map", "[final_v]", "-map", "[concat_a]",
                "-c:v", "libx264", "-crf", str(crf_value), "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p", "-aspect", "9:16", intermediate_scenes_clip_path
            ])
        
        intermediate_scenes_result = subprocess.run(cmd_create_intermediate_scenes, capture_output=True, text=True)
        if intermediate_scenes_result.returncode != 0:
            print(f"  ⚠️ Erro ao criar clipe intermediário '{intermediate_scenes_clip_name}':\n     {intermediate_scenes_result.stderr}")
            continue
        print(f"  ✅ Clipe intermediário '{intermediate_scenes_clip_name}' criado.")

        print(f"  -> Etapa 2/2: Gerando edição final '{output_edit_filename_quality}'...")
        cmd_final_concat = ["ffmpeg", "-y"]
        input_files_for_final_concat = [intermediate_scenes_clip_path]

        if path_for_ebook_in_filelist and os.path.exists(temp_ebook_clip_path):
            input_files_for_final_concat.append(temp_ebook_clip_path)
        
        for input_file in input_files_for_final_concat:
            cmd_final_concat.extend(["-i", input_file])

        if len(input_files_for_final_concat) == 1:
            cmd_final_concat.extend([
                "-c:v", "libx264", "-crf", str(crf_value), "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p", "-aspect", "9:16", output_edit_filename_quality
            ])
        else:
            filter_complex_final_str = "".join([f"[{i_final}:v:0][{i_final}:a:0]" for i_final in range(len(input_files_for_final_concat))])
            filter_complex_final_str += f"concat=n={len(input_files_for_final_concat)}:v=1:a=1[outv][outa]"
            cmd_final_concat.extend([
                "-filter_complex", filter_complex_final_str, "-map", "[outv]", "-map", "[outa]",
                "-c:v", "libx264", "-crf", str(crf_value), "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p", "-aspect", "9:16", output_edit_filename_quality
            ])

        final_concat_result = subprocess.run(cmd_final_concat, capture_output=True, text=True)
        
        # Verifica se o arquivo de saída existe APÓS a execução do ffmpeg
        output_file_exists = os.path.exists(output_edit_filename_quality)

        if final_concat_result.returncode == 0 and output_file_exists:
            # Garante que o caminho seja absoluto para clareza no log
            abs_output_path = os.path.abspath(output_edit_filename_quality)
            print(f"  ✅ Edição final '{os.path.basename(output_edit_filename_quality)}' criada!")
            print(f"     Salvo em: {abs_output_path}")
        else:
            print(f"  ⚠️ Erro ao criar edição final '{output_edit_filename_quality}'.")
            if final_concat_result.returncode != 0:
                print(f"     Código de retorno FFmpeg: {final_concat_result.returncode}")
                print(f"     Stderr FFmpeg:\n{final_concat_result.stderr.strip()}")
            if not output_file_exists:
                print(f"     AVISO: Arquivo de saída '{output_edit_filename_quality}' não encontrado no disco após o comando, mesmo que FFmpeg não tenha reportado erro fatal.")

    shutil.rmtree(temp_dir)
    print(f"  Diretório temporário '{temp_dir}' removido.")


def gerar_edit_json_pelas_batidas(
    caminho_arquivo_batidas,
    pasta_frames_video_fonte, 
    nome_video_fonte_no_json,
    nome_audio_fonte_no_json,
    generate_edit_config, 
    pasta_videos_baixados, 
    caminho_saida_edit_json="edit.json" # Este caminho será ajustado em main.py
    ):
    """
    Gera um arquivo edit.json usando os tempos de um arquivo de batidas e frames/cenas.
    """
    print(f"\n🔄 Gerando '{os.path.basename(caminho_saida_edit_json)}' a partir de batidas...")
    if not caminho_arquivo_batidas or not os.path.exists(caminho_arquivo_batidas):
        print(f"⚠️ Arquivo de batidas não encontrado: {caminho_arquivo_batidas}")
        return False
    
    min_duration_sec = generate_edit_config.get("min_scene_duration_seconds", 2.0)
    use_scenes_from_detection = generate_edit_config.get("use_scenes", False)

    try:
        with open(caminho_arquivo_batidas, "r", encoding='utf-8') as f:
            beat_timestamps_hhmmssff = [line.strip() for line in f if line.strip()]

        if len(beat_timestamps_hhmmssff) < 2:
            print(f"⚠️ Batidas insuficientes em '{os.path.basename(caminho_arquivo_batidas)}' (necessário >= 2).")
            return False

        available_frame_numbers = []
        detected_scenes_data = []

        if use_scenes_from_detection:
            path_cenas_detectadas = os.path.join(pasta_videos_baixados, "cenas_detectadas.json")
            if os.path.exists(path_cenas_detectadas):
                with open(path_cenas_detectadas, "r", encoding='utf-8') as f_scenes:
                    detected_scenes_data = json.load(f_scenes)
                if not detected_scenes_data:
                    print(f"⚠️ 'cenas_detectadas.json' vazio. Usando frames aleatórios.")
                    use_scenes_from_detection = False
                else:
                    print(f"   Usando cenas de: {path_cenas_detectadas}")
            else:
                print(f"⚠️ 'cenas_detectadas.json' não encontrado. Usando frames aleatórios.")
                use_scenes_from_detection = False

        if not use_scenes_from_detection: # Fallback ou modo frame
            if not os.path.exists(pasta_frames_video_fonte):
                print(f"⚠️ Pasta de frames '{pasta_frames_video_fonte}' não encontrada.")
                return False
            print(f"   Usando frames aleatórios de: {pasta_frames_video_fonte}")
            available_frames_files = [f for f in os.listdir(pasta_frames_video_fonte) if f.startswith("frame_") and f.lower().endswith(".jpg")]
            if not available_frames_files:
                print(f"⚠️ Nenhum frame encontrado em '{pasta_frames_video_fonte}'.")
                return False
            for frame_file in available_frames_files:
                try:
                    available_frame_numbers.append(str(int(frame_file.split('_')[1])))
                except (ValueError, IndexError):
                    pass # Ignora arquivos malformados
            if not available_frame_numbers:
                print(f"⚠️ Nenhum número de frame válido extraído de '{pasta_frames_video_fonte}'.")
                return False

        fps_for_parsing = 25 
        scenes = []
        i = 0
        while i < len(beat_timestamps_hhmmssff) - 1:
            audio_start_str = beat_timestamps_hhmmssff[i]
            suitable_audio_end_str = None
            next_beat_index_for_end = i + 1

            while next_beat_index_for_end < len(beat_timestamps_hhmmssff):
                potential_audio_end_str = beat_timestamps_hhmmssff[next_beat_index_for_end]
                try:
                    duration_sec = parse_hhmmssff_to_seconds(potential_audio_end_str, fps=fps_for_parsing) - \
                                   parse_hhmmssff_to_seconds(audio_start_str, fps=fps_for_parsing)
                    if duration_sec >= min_duration_sec:
                        suitable_audio_end_str = potential_audio_end_str
                        break
                except ValueError: # Ignora timestamps malformados
                    pass
                next_beat_index_for_end += 1

            if suitable_audio_end_str:
                scene_entry = {"audio_start": audio_start_str, "audio_end": suitable_audio_end_str}
                added_scene_content = False

                if use_scenes_from_detection and detected_scenes_data:
                    current_audio_duration = parse_hhmmssff_to_seconds(suitable_audio_end_str, fps=fps_for_parsing) - \
                                           parse_hhmmssff_to_seconds(audio_start_str, fps=fps_for_parsing)
                    candidate_detected_scenes = [s for s in detected_scenes_data if (s['fim_segundos'] - s['inicio_segundos']) >= current_audio_duration]
                    
                    if candidate_detected_scenes:
                        chosen_scene = random.choice(candidate_detected_scenes)
                        scene_entry["scene_cuted"] = chosen_scene["cena_numero"]
                        added_scene_content = True
                    elif len(detected_scenes_data) >= 1 : # Fallback se não houver cena com duração suficiente
                        chosen_scene = random.choice(detected_scenes_data) # Pega qualquer cena
                        scene_entry["scene_cuted"] = chosen_scene["cena_numero"]
                        added_scene_content = True
                        # print(f"   Fallback: Usando cena detectada nº {chosen_scene['cena_numero']} (duração do áudio será mantida).")

                elif not use_scenes_from_detection and available_frame_numbers: # Modo frame ou fallback final
                    scene_entry["frame"] = random.choice(available_frame_numbers)
                    added_scene_content = True

                if added_scene_content:
                    scenes.append(scene_entry)
                i = next_beat_index_for_end
            else:
                i += 1 # Avança para a próxima batida inicial potencial

        edit_data = {
            "source_video": nome_video_fonte_no_json,
            "source_audio": nome_audio_fonte_no_json,
            "scenes": scenes
        }

        with open(caminho_saida_edit_json, "w", encoding='utf-8') as f:
            json.dump(edit_data, f, indent=4, ensure_ascii=False)
        print(f"✅ '{os.path.basename(caminho_saida_edit_json)}' gerado com {len(scenes)} cenas.")
        return True
    except Exception as e:
        print(f"⚠️ Erro ao gerar '{os.path.basename(caminho_saida_edit_json)}': {e}")
        import traceback
        traceback.print_exc()
        return False