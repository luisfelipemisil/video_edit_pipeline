import os
import subprocess
import time # Adicionado para a pausa entre tentativas
import cv2 # Adicionado para manipulação de vídeo

def extrair_frames(video_path, pasta_frames_saida, intervalo_segundos=1, qualidade_jpeg=55):
    """
    Extrai frames de um vídeo em intervalos regulares e retorna seus caminhos e timestamps.

    Args:
        video_path (str): Caminho para o arquivo de vídeo.
        pasta_frames_saida (str): Pasta onde os frames extraídos serão salvos.
        intervalo_segundos (float): Intervalo em segundos para extrair frames.
                                     Ex: 1 para um frame por segundo.
        qualidade_jpeg (int): Qualidade para salvar frames JPEG (0-100).
                              Padrão é 75.
    
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
    Baixa um vídeo usando yt-dlp e retorna o caminho do arquivo baixado.
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
            return None
        
        # Etapa 2: Construir o caminho de destino absoluto final e realizar o download
        path_destino_abs = os.path.abspath(path_destino_param)
        if not os.path.exists(path_destino_abs):
            try:
                os.makedirs(path_destino_abs, exist_ok=True)
            except OSError as e:
                print(f"⚠️ Erro ao criar pasta de destino {path_destino_abs}: {e}")
                return None
        
        final_intended_path = os.path.join(path_destino_abs, resolved_filename)
        print(f"   Tentando salvar em: {final_intended_path}")

        # Etapa 2.1: Verificar se o vídeo já existe no caminho final pretendido
        if os.path.exists(final_intended_path):
            print(f"✅ Vídeo já baixado: {os.path.basename(final_intended_path)}")
            print(f"   Localizado em: {final_intended_path}")
            return final_intended_path

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
                return final_intended_path
            else:
                print(f"⚠️ Download parece ter sido bem-sucedido (código 0), mas o arquivo '{final_intended_path}' não foi encontrado após {max_retries} tentativas.")
                print(f"   Saída do download yt-dlp (stdout):\n{download_process.stdout}")
                print(f"   Saída do download yt-dlp (stderr):\n{download_process.stderr}")
                return None
        else:
            print(f"⚠️ Erro ao baixar/processar {url} com yt-dlp.")
            print(f"   Código de retorno: {download_process.returncode}")
            print(f"   Saída yt-dlp (stdout):\n{download_process.stdout}")
            print(f"   Saída yt-dlp (stderr):\n{download_process.stderr}")
            return None

    except subprocess.CalledProcessError as e: # Erro ao obter o nome do arquivo
        print(f"⚠️ Erro ao tentar obter o nome do arquivo com yt-dlp para {url}: {e}")
        print(f"   Comando: {' '.join(e.cmd)}")
        print(f"   Saída yt-dlp (stdout):\n{e.stdout}")
        print(f"   Saída yt-dlp (stderr):\n{e.stderr}")
        return None
    except FileNotFoundError: # yt-dlp não encontrado
        print("⚠️ Erro: yt-dlp não encontrado. Verifique se está instalado e no PATH do sistema.")
        return None
    except Exception as e:
        print(f"⚠️ Erro inesperado ao tentar baixar {url}: {e}")
        return None

def baixar_videos_da_lista(arquivo_lista, path_destino=".", intervalo_extracao_frames_seg=1, qualidade_jpeg_frames=75):
    if not os.path.exists(arquivo_lista):
        print(f"Arquivo de lista não encontrado: {arquivo_lista}")
        return
    
    if not os.path.exists(path_destino):
        try:
            os.makedirs(path_destino)
            print(f"Pasta de destino principal criada: {path_destino}")
        except OSError as e:
            print(f"⚠️ Erro ao criar pasta de destino principal {path_destino}: {e}")
            return
            
    with open(arquivo_lista, "r", encoding='utf-8') as f: # Adicionado encoding
        links = [linha.strip() for linha in f if linha.strip() and not linha.startswith("#")] # Ignora linhas vazias e comentários
    
    if not links:
        print(f"Nenhum link encontrado em {arquivo_lista}.")
        return

    print(f"\nIniciando download de {len(links)} vídeo(s) da lista '{arquivo_lista}'...")
    for link in links:
        caminho_video_baixado = baixar_video(link, path_destino)
        
        if caminho_video_baixado:
            # Criar uma pasta específica para os frames deste vídeo
            nome_base_video = os.path.splitext(os.path.basename(caminho_video_baixado))[0]
            pasta_frames_video = os.path.join(path_destino, f"{nome_base_video}_frames")
            
            frames_info = extrair_frames(caminho_video_baixado, pasta_frames_video, intervalo_extracao_frames_seg, qualidade_jpeg_frames)
            
            if frames_info:
                # Aqui você tem a lista de frames e seus timestamps
                # Exemplo: imprimir os primeiros 5 para verificação
                # print(f"   Primeiros frames extraídos para '{nome_base_video}':")
                # for i, (frame_path, timestamp) in enumerate(frames_info[:5]):
                #    print(f"     - Frame: {os.path.basename(frame_path)}, Timestamp: {timestamp:.2f}s")
                # print("   ...")
                # Você pode usar 'frames_info' para enviar ao Gemini.
                pass # A função extrair_frames já imprime o status
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

    baixar_videos_da_lista(arquivo_links, pasta_destino_videos, intervalo_para_frames_seg, qualidade_dos_frames_jpeg)
    print("\nProcesso concluído.")
