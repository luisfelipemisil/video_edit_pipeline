import os
import subprocess
import time # Adicionado para a pausa entre tentativas
import cv2 # Adicionado para manipulação de vídeo
import google.generativeai as genai
import json # Para processar respostas JSON do Gemini, se aplicável
from dotenv import load_dotenv # Adicionado para carregar o .env
import google.api_core.exceptions # For catching specific API errors

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração da API Key do Gemini (idealmente via variável de ambiente)
try:
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
    if GOOGLE_API_KEY:
        genai.configure(api_key=GOOGLE_API_KEY)
    else:
        print("⚠️ GOOGLE_API_KEY não encontrada no ambiente. Verifique seu arquivo .env ou variáveis de ambiente.")
except Exception as e:
    print(f"⚠️ Erro ao configurar a API Gemini: {e}. Verifique se GOOGLE_API_KEY está definida.")
    # Decide se quer sair ou continuar sem a funcionalidade do Gemini
    # exit() 

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

def analisar_com_gemini(caminho_musica, frames_info):
    """
    Envia o áudio e os frames para o Gemini analisar e sugerir trechos para um edit.

    Args:
        caminho_musica (str): Caminho para o arquivo de áudio.
        frames_info (list): Lista de tuplas (caminho_do_frame, timestamp_em_segundos).

    Returns:
        dict or None: Um dicionário com as sugestões do Gemini ou None em caso de erro.
                      Exemplo de retorno esperado:
                      {
                          "audio_snippet": {"start_sec": S, "end_sec": E},
                          "video_scenes": [
                              {"start_sec": V1_S, "end_sec": V1_E, "frame_path": FP1},
                              {"start_sec": V2_S, "end_sec": V2_E, "frame_path": FP2}
                          ]
                      }
    """
    if not GOOGLE_API_KEY:
        print("⚠️ API Key do Gemini não configurada. Análise com Gemini não será realizada.")
        return None

    print("\n🤖 Analisando com Gemini...")
    try:
        # Escolha um modelo Gemini que suporte multimodalidade (ex: gemini-1.5-pro)
        # Verifique a documentação para o modelo mais recente e adequado.
        model = genai.GenerativeModel('gemini-1.5-pro-latest') 

        # 1. Fazer upload dos arquivos para a API Gemini
        print(f"   Fazendo upload do arquivo de áudio: {caminho_musica}...")
        audio_file_uploaded = genai.upload_file(path=caminho_musica)
        print(f"   Upload do áudio concluído: {audio_file_uploaded.name}")

        # Para os frames, podemos enviar alguns representativos ou todos, dependendo dos limites da API
        # e da estratégia. Para este exemplo, vamos assumir que podemos referenciá-los.
        # A API Gemini pode lidar com uma lista de partes, incluindo texto e arquivos.
        
        # Construir o prompt
        # Este prompt é um exemplo e pode precisar de muitos refinamentos.
        prompt_parts = [
            "Você é um editor de vídeo especialista em criar conteúdo viral para o TikTok com estética cyberpunk.",
            "Analise o seguinte arquivo de áudio:",
            audio_file_uploaded, # Referência ao arquivo de áudio carregado
            f"O áudio tem duração X segundos. (Você precisaria obter a duração do áudio aqui se o Gemini não fizer isso automaticamente)",
            "Agora, considere a seguinte sequência de frames de um vídeo. Cada frame tem um timestamp associado:",
        ]

        # Adicionar informações dos frames ao prompt (pode ser uma lista de caminhos ou referências)
        # Se for enviar os frames, eles também precisariam ser carregados com genai.upload_file
        # Por simplicidade, vamos descrever os frames e seus timestamps.
        # Em uma implementação real, você pode enviar os arquivos de imagem se a API permitir um grande número.
        prompt_parts.append("Frames do vídeo (timestamp em segundos):")
        for frame_path, timestamp in frames_info[:5]: # Exemplo: enviando info dos primeiros 20 frames
            # Reduzido para 5 frames para teste de quota, ajuste conforme necessário
        # for frame_path, timestamp in frames_info[:5]: 
            prompt_parts.append(f"- Frame: {os.path.basename(frame_path)} at {timestamp:.2f}s") # Use o loop original
            # Se fosse fazer upload:
            # uploaded_frame = genai.upload_file(path=frame_path)
            # prompt_parts.append(uploaded_frame)
    
        prompt_parts.extend([
            "\nTarefa:",
            "1. No áudio fornecido, identifique um trecho curto (5-15 segundos) que seja empolgante e adequado para um edit cyberpunk no TikTok.",
            "2. Nos frames do vídeo fornecidos, selecione uma sequência de cenas que se encaixem visualmente e ritmicamente com o trecho de áudio escolhido. As cenas devem fluir bem em sequência.",
            "3. Retorne sua sugestão no seguinte formato JSON:",
            "   {\"audio_snippet\": {\"start_sec\": <início_audio_seg>, \"end_sec\": <fim_audio_seg>}, \"video_scenes\": [{\"start_sec\": <início_cena1_seg>, \"end_sec\": <fim_cena1_seg>}, {\"start_sec\": <início_cena2_seg>, \"end_sec\": <fim_cena2_seg>}]}",
            "   Certifique-se de que os timestamps de vídeo correspondam aos timestamps dos frames fornecidos."
        ])

        max_gemini_retries = 3
        # Initial delay based on a common suggestion, but will try to use API's suggestion
        gemini_retry_delay_base_seconds = 30 

        for attempt in range(max_gemini_retries):
            try:
                print(f"   Enviando prompt para o Gemini (tentativa {attempt + 1}/{max_gemini_retries})...")
                response = model.generate_content(prompt_parts)
                
                print("   Resposta recebida do Gemini.")
                # Tentar processar a resposta como JSON
                try:
                    cleaned_response_text = response.text.strip()
                    if cleaned_response_text.startswith("```json"):
                        cleaned_response_text = cleaned_response_text[7:]
                    if cleaned_response_text.endswith("```"):
                        cleaned_response_text = cleaned_response_text[:-3]
                    
                    sugestoes = json.loads(cleaned_response_text)
                    return sugestoes # Success
                except (json.JSONDecodeError, AttributeError, TypeError) as e_json:
                    print(f"⚠️ Não foi possível decodificar a resposta do Gemini como JSON: {e_json}")
                    print(f"   Resposta bruta do Gemini:\n{response.text}")
                    return None # JSON processing error, don't retry this specific error

            except google.api_core.exceptions.ResourceExhausted as e_quota: # Specific error for 429
                print(f"⚠️ Erro de cota do Gemini (429): {e_quota}")
                if attempt < max_gemini_retries - 1:
                    delay_seconds = gemini_retry_delay_base_seconds
                    # Try to parse suggested retry_delay from the error metadata
                    if hasattr(e_quota, 'metadata') and e_quota.metadata:
                        for item in e_quota.metadata:
                            if item.key == 'retry_delay' and hasattr(item.value, 'seconds'):
                                try:
                                    delay_seconds = int(item.value.seconds) + 2 # Add a small buffer
                                    print(f"   API sugeriu aguardar {item.value.seconds}s.")
                                    break
                                except (ValueError, AttributeError):
                                    pass # Use default if parsing fails
                    
                    print(f"   Aguardando {delay_seconds} segundos antes de tentar novamente...")
                    time.sleep(delay_seconds)
                    gemini_retry_delay_base_seconds *= 2 # Exponential backoff for next default
                else:
                    print("   Máximo de tentativas com Gemini atingido devido a erro de cota.")
                    return None # Failed after all retries
            except Exception as e_general: # Catch other potential errors during API call
                print(f"⚠️ Erro inesperado durante a chamada à API Gemini: {e_general}")
                return None # Don't retry general errors
        
        return None # Should only be reached if all retries for quota error fail
    except Exception as e:
        print(f"⚠️ Erro durante a análise com Gemini: {e}")
        # Em caso de erro com upload_file, pode ser útil limpar arquivos temporários se a API os criar.
        # if 'audio_file_uploaded' in locals() and audio_file_uploaded:
        # genai.delete_file(audio_file_uploaded.name) # Exemplo de limpeza
        return None

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
                    print(f"🎶 Música para análise: {caminho_musica}")
                    
                    sugestoes_gemini = analisar_com_gemini(caminho_musica, frames_info)

                    if sugestoes_gemini:
                        print("\n✨ Sugestões do Gemini para o Edit:")
                        if "audio_snippet" in sugestoes_gemini:
                            print(f"   🎤 Trecho do Áudio: {sugestoes_gemini['audio_snippet']['start_sec']:.2f}s - {sugestoes_gemini['audio_snippet']['end_sec']:.2f}s")
                        if "video_scenes" in sugestoes_gemini:
                            print("   🎬 Cenas do Vídeo Sugeridas:")
                            for i, cena in enumerate(sugestoes_gemini['video_scenes']):
                                print(f"      - Cena {i+1}: {cena['start_sec']:.2f}s - {cena['end_sec']:.2f}s")
                elif caminho_musica:
                    print(f"⚠️ Música especificada ({caminho_musica}) não encontrada. Análise com música não será possível para este vídeo.")
            # else: (extrair_frames já imprime erros ou status de nenhum frame)
        else:
            print(f"Download de {link} falhou ou foi pulado. Não será possível extrair frames.")
        print("-" * 30) # Separador entre vídeos

# Exemplo de uso
if __name__ == "__main__":
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
