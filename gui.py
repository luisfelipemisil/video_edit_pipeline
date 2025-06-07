# /Users/lfms/Documents/projeto_cut_videos/gui.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import json
import os
import subprocess
import threading
import queue
import sys # Adicionado para sys.executable

# --- Constantes de Caminhos ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_PATH = os.path.join(BASE_DIR, "src", "config", "config.json") # Ajustado
LINKS_FILE_PATH = os.path.join(BASE_DIR, "src", "data", "links.txt")     # Ajustado
MUSICA_FILE_PATH = os.path.join(BASE_DIR, "src", "data", "musica.txt")   # Ajustado
SRC_DIR = os.path.join(BASE_DIR, "src") # Para garantir que o comando python -m funcione

# --- Configurações Padrão (para o caso do arquivo não existir) ---
DEFAULT_CONFIG = {
    "baixar_videos_da_lista": True,
    "extrair_frames_dos_videos": True,
    "baixar_audio_da_musica": True,
    "analisar_batidas_do_audio": True,
    "filtrar_batidas_por_amplitude": {"enabled": True, "min_amplitude_percentage": 75},
    "criar_edit_final_do_json": False,
    "generate_edit_from_beats": {"enabled": False, "min_scene_duration_seconds": 2.0, "use_scenes": False},
    "detectar_cortes_de_cena_video": {"enabled": True, "video_source_index": 0, "threshold": 27.0},
    "output_qualities": [{"name": "default", "crf": 23}], # Alterado para um único default
    "movie_name": ""
}

class PipelineGUI:
    def __init__(self, master):
        self.master = master
        master.title("Pipeline de Edição de Vídeo")
        master.geometry("800x700")

        self.config_vars = {}
        self.config_data = {}
        self.string_vars = {} # Para Entries e Spinboxes que retornam string
        self.last_log_was_ffmpeg_progress = False # Rastrear última linha de log

        # --- Layout Principal ---
        main_frame = ttk.Frame(master, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Notebook para abas de configuração
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.X, pady=5)

        # --- Frame de Configurações ---
        general_config_tab = ttk.Frame(notebook, padding="10")
        notebook.add(general_config_tab, text="Opções Principais")
        self.populate_general_config_tab(general_config_tab)

        # --- Frame de Configurações Detalhadas ---
        detailed_config_tab = ttk.Frame(notebook, padding="10")
        notebook.add(detailed_config_tab, text="Ajustes Finos")
        self.populate_detailed_config_tab(detailed_config_tab)



        # --- Frame de Entradas ---
        inputs_frame = ttk.LabelFrame(main_frame, text="Entradas", padding="10")
        inputs_frame.pack(fill=tk.X, pady=5)

        ttk.Label(inputs_frame, text="URL da Música (musica.txt):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.musica_url_entry = ttk.Entry(inputs_frame, width=80)
        self.musica_url_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2)

        ttk.Label(inputs_frame, text="Links dos Vídeos (links.txt, um por linha):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.links_videos_text = tk.Text(inputs_frame, height=5, width=80)
        self.links_videos_text.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=2)
        inputs_frame.columnconfigure(1, weight=1)


        # --- Botão de Execução ---
        self.run_button = ttk.Button(main_frame, text="Rodar Pipeline", command=self.run_pipeline_thread)
        self.run_button.pack(pady=10)

        # --- Frame de Logs ---
        logs_frame = ttk.LabelFrame(main_frame, text="Logs", padding="10")
        logs_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.logs_text = scrolledtext.ScrolledText(logs_frame, height=15, width=100, wrap=tk.WORD, state=tk.DISABLED)
        self.logs_text.pack(fill=tk.BOTH, expand=True)

        self.load_config_file()
        self.load_data_files()

        self.log_queue = queue.Queue()
        self.master.after(100, self.process_log_queue)

    def populate_general_config_tab(self, parent_tab):
        # Chaves a serem exibidas como checkboxes
        # (Chave no JSON, Texto do Label na GUI)
        checkbox_keys = [
            ("baixar_videos_da_lista", "Baixar Vídeos da Lista"), # Mantido para exemplo, pode ser movido
            ("extrair_frames_dos_videos", "Extrair Frames dos Vídeos"),
            ("baixar_audio_da_musica", "Baixar Áudio da Música"),
            ("analisar_batidas_do_audio", "Analisar Batidas do Áudio"),
            ("filtrar_batidas_por_amplitude.enabled", "Filtrar Batidas por Amplitude"),
            ("detectar_cortes_de_cena_video.enabled", "Detectar Cortes de Cena"),
            ("generate_edit_from_beats.enabled", "Gerar edit.json pelas Batidas"),
            ("criar_edit_final_do_json", "Criar Edit Final do JSON"),
        ]

        row = 0
        col = 0
        for key_path, label_text in checkbox_keys:
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(parent_tab, text=label_text, variable=var)
            cb.grid(row=row, column=col, sticky=tk.W, padx=5, pady=2)
            self.config_vars[key_path] = var
            col += 1
            if col >= 2:
                col = 0
                row += 1

    def populate_detailed_config_tab(self, parent_tab):
        current_row = 0

        # --- Filtrar Batidas por Amplitude ---
        filter_beats_frame = ttk.LabelFrame(parent_tab, text="Filtro de Batidas", padding="5")
        filter_beats_frame.grid(row=current_row, column=0, padx=5, pady=5, sticky=tk.EW)
        current_row += 1

        ttk.Label(filter_beats_frame, text="Min. Amplitude (%):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        amp_var = tk.StringVar()
        amp_spinbox = ttk.Spinbox(filter_beats_frame, from_=0, to=100, increment=1, textvariable=amp_var, width=5)
        amp_spinbox.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        self.string_vars["filtrar_batidas_por_amplitude.min_amplitude_percentage"] = amp_var

        # --- Gerar edit.json pelas Batidas ---
        gen_edit_frame = ttk.LabelFrame(parent_tab, text="Geração Automática de Edit.json", padding="5")
        gen_edit_frame.grid(row=current_row, column=0, padx=5, pady=5, sticky=tk.EW)
        current_row += 1

        use_scenes_var = tk.BooleanVar()
        use_scenes_cb = ttk.Checkbutton(gen_edit_frame, text="Usar Cenas Detectadas (em vez de frames)", variable=use_scenes_var)
        use_scenes_cb.grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        self.config_vars["generate_edit_from_beats.use_scenes"] = use_scenes_var

        ttk.Label(gen_edit_frame, text="Duração Mín. Cena (s):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        min_dur_var = tk.StringVar()
        min_dur_spinbox = ttk.Spinbox(gen_edit_frame, from_=0.1, to=60.0, increment=0.1, format="%.1f", textvariable=min_dur_var, width=5)
        min_dur_spinbox.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
        self.string_vars["generate_edit_from_beats.min_scene_duration_seconds"] = min_dur_var

        # --- Detecção de Cortes de Cena ---
        scene_detect_frame = ttk.LabelFrame(parent_tab, text="Detecção de Cortes de Cena", padding="5")
        scene_detect_frame.grid(row=current_row, column=0, padx=5, pady=5, sticky=tk.EW)
        current_row += 1

        ttk.Label(scene_detect_frame, text="Índice Vídeo (links.txt):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        vid_idx_var = tk.StringVar()
        vid_idx_spinbox = ttk.Spinbox(scene_detect_frame, from_=0, to=100, increment=1, textvariable=vid_idx_var, width=5)
        vid_idx_spinbox.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        self.string_vars["detectar_cortes_de_cena_video.video_source_index"] = vid_idx_var

        ttk.Label(scene_detect_frame, text="Threshold Detecção:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        thresh_var = tk.StringVar()
        thresh_spinbox = ttk.Spinbox(scene_detect_frame, from_=1.0, to=100.0, increment=0.1, format="%.1f", textvariable=thresh_var, width=5)
        thresh_spinbox.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
        self.string_vars["detectar_cortes_de_cena_video.threshold"] = thresh_var

        # --- Configurações de Saída ---
        output_frame = ttk.LabelFrame(parent_tab, text="Saída", padding="5")
        output_frame.grid(row=current_row, column=0, padx=5, pady=5, sticky=tk.EW)
        current_row += 1

        ttk.Label(output_frame, text="Nome do Filme:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        movie_name_var = tk.StringVar()
        movie_name_entry = ttk.Entry(output_frame, textvariable=movie_name_var, width=30)
        movie_name_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2)
        self.string_vars["movie_name"] = movie_name_var

        ttk.Label(output_frame, text="CRF Padrão (Qualidade):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        crf_var = tk.StringVar()
        crf_spinbox = ttk.Spinbox(output_frame, from_=0, to=51, increment=1, textvariable=crf_var, width=5)
        crf_spinbox.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
        self.string_vars["output_qualities.0.crf"] = crf_var # Simplificado: afeta o primeiro item de output_qualities

        parent_tab.columnconfigure(0, weight=1)



    def load_config_file(self):
        try:
            if os.path.exists(CONFIG_FILE_PATH):
                with open(CONFIG_FILE_PATH, "r", encoding='utf-8') as f:
                    self.config_data = json.load(f)
            else:
                self.config_data = DEFAULT_CONFIG.copy()
                self.log_message(f"Arquivo de configuração não encontrado. Usando padrões e criando '{CONFIG_FILE_PATH}'.")
                # Salva o default para o usuário ter um ponto de partida
                with open(CONFIG_FILE_PATH, "w", encoding='utf-8') as f:
                    json.dump(self.config_data, f, indent=4, ensure_ascii=False)

        except json.JSONDecodeError:
            self.log_message(f"Erro ao decodificar {CONFIG_FILE_PATH}. Usando configurações padrão.")
            self.config_data = DEFAULT_CONFIG.copy()
        except Exception as e:
            self.log_message(f"Erro ao carregar {CONFIG_FILE_PATH}: {e}. Usando configurações padrão.")
            self.config_data = DEFAULT_CONFIG.copy()

        # Atualizar checkboxes
        for key_path, tk_var in self.config_vars.items():
            keys = key_path.split('.')
            value = self.config_data
            try:
                for k in keys:
                    value = value[k]
                if isinstance(value, bool):
                    tk_var.set(value)
            except (KeyError, TypeError):
                tk_var.set(False)

        # Atualizar StringVars (Entries, Spinboxes)
        for key_path, str_var in self.string_vars.items():
            keys = key_path.split('.')
            value = self.config_data
            try:
                for k_idx, k_part in enumerate(keys):
                    if k_part.isdigit() and isinstance(value, list): # Para listas como output_qualities.0.crf
                        value = value[int(k_part)]
                    elif isinstance(value, dict):
                        value = value[k_part]
                    else: # Caminho inválido na config
                        raise KeyError
                str_var.set(str(value))
            except (KeyError, TypeError, IndexError):
                # Se a chave não existir ou o tipo for incompatível, tenta pegar do DEFAULT_CONFIG
                # Isso é um pouco mais complexo para caminhos aninhados, então pode precisar de ajuste fino
                str_var.set("") # Ou um valor padrão específico

    def save_config_file(self):
        # Garante que self.config_data está atualizado com os padrões se não foi carregado
        if not self.config_data:
            self.config_data = DEFAULT_CONFIG.copy()

        for key_path, var in self.config_vars.items():
            keys = key_path.split('.') # e.g., "generate_edit_from_beats.use_scenes"
            current_level = self.config_data
            for i, k_part in enumerate(keys[:-1]):
                if k_part not in current_level or not isinstance(current_level[k_part], dict):
                    current_level[k_part] = {} # Cria sub-dicionário se não existir
                current_level = current_level[k_part]
            current_level[keys[-1]] = var.get()

        for key_path, str_var in self.string_vars.items():
            keys = key_path.split('.') # e.g., "output_qualities.0.crf"
            value_to_set = str_var.get()
            current_level = self.config_data

            for i, k_part in enumerate(keys[:-1]):
                if k_part.isdigit() and isinstance(current_level, list): # Acessando índice de lista
                    idx = int(k_part)
                    while len(current_level) <= idx: # Garante que a lista tenha tamanho suficiente
                        current_level.append({}) # Adiciona dicionários vazios se necessário
                    if not isinstance(current_level[idx], dict): # Garante que o elemento da lista seja um dict
                        current_level[idx] = {}
                    current_level = current_level[idx]
                elif isinstance(current_level, dict): # Acessando chave de dicionário
                    if k_part not in current_level or not isinstance(current_level[k_part], (dict, list)):
                        # Se o próximo nível for um índice de lista, prepare uma lista
                        if i + 1 < len(keys) and keys[i+1].isdigit():
                            current_level[k_part] = []
                        else:
                            current_level[k_part] = {}
                    current_level = current_level[k_part]
                else: # Caminho inválido
                    break 
            else: # Se o loop completou sem break
                # Tenta converter para o tipo apropriado (int, float, ou mantém string)
                try: value_to_set = int(value_to_set)
                except ValueError:
                    try: value_to_set = float(value_to_set)
                    except ValueError: pass # Mantém como string
                
                if keys[-1].isdigit() and isinstance(current_level, list):
                    idx = int(keys[-1])
                    while len(current_level) <= idx: current_level.append(None)
                    current_level[idx] = value_to_set
                elif isinstance(current_level, dict):
                    current_level[keys[-1]] = value_to_set

        try:
            # Garante que o diretório de configuração exista
            config_dir = os.path.dirname(CONFIG_FILE_PATH)
            os.makedirs(config_dir, exist_ok=True)

            # Simplificação para output_qualities: garante que o nome seja "default" se o CRF for definido pela GUI
            if "output_qualities.0.crf" in self.string_vars:
                if self.config_data.get("output_qualities") and isinstance(self.config_data["output_qualities"], list):
                    if len(self.config_data["output_qualities"]) > 0 and isinstance(self.config_data["output_qualities"][0], dict):
                        self.config_data["output_qualities"][0]["name"] = "default_gui" # ou apenas "default"
                    elif not self.config_data["output_qualities"]: # Lista vazia
                         self.config_data["output_qualities"].append({"name": "default_gui", "crf": int(self.string_vars["output_qualities.0.crf"].get() or 23)})
                else: # output_qualities não existe ou não é lista
                    self.config_data["output_qualities"] = [{"name": "default_gui", "crf": int(self.string_vars["output_qualities.0.crf"].get() or 23)}]


            with open(CONFIG_FILE_PATH, "w", encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
            self.log_message(f"Configurações salvas em '{CONFIG_FILE_PATH}'.")
        except Exception as e:
            self.log_message(f"Erro ao salvar configurações: {e}")
            messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar o arquivo de configuração:\n{e}")


    def load_data_files(self):
        try:
            if os.path.exists(MUSICA_FILE_PATH):
                with open(MUSICA_FILE_PATH, "r", encoding='utf-8') as f:
                    self.musica_url_entry.delete(0, tk.END)
                    self.musica_url_entry.insert(0, f.readline().strip())
            else:
                self.log_message(f"'{MUSICA_FILE_PATH}' não encontrado. Crie-o ou insira a URL.")

            if os.path.exists(LINKS_FILE_PATH):
                with open(LINKS_FILE_PATH, "r", encoding='utf-8') as f:
                    self.links_videos_text.delete("1.0", tk.END)
                    self.links_videos_text.insert("1.0", f.read())
            else:
                self.log_message(f"'{LINKS_FILE_PATH}' não encontrado. Crie-o ou insira os links.")
        except Exception as e:
            self.log_message(f"Erro ao carregar arquivos de dados: {e}")

    def save_data_files(self):
        try:
            # Garante que os diretórios existam
            os.makedirs(os.path.dirname(MUSICA_FILE_PATH), exist_ok=True)
            os.makedirs(os.path.dirname(LINKS_FILE_PATH), exist_ok=True)

            with open(MUSICA_FILE_PATH, "w", encoding='utf-8') as f:
                f.write(self.musica_url_entry.get().strip() + "\n")
            self.log_message(f"URL da música salva em '{MUSICA_FILE_PATH}'.")

            with open(LINKS_FILE_PATH, "w", encoding='utf-8') as f:
                f.write(self.links_videos_text.get("1.0", tk.END).strip() + "\n")
            self.log_message(f"Links dos vídeos salvos em '{LINKS_FILE_PATH}'.")
        except Exception as e:
            self.log_message(f"Erro ao salvar arquivos de dados: {e}")
            messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar os arquivos de dados:\n{e}")

    def log_message(self, message):
        self.logs_text.config(state=tk.NORMAL)
        self.logs_text.insert(tk.END, message + "\n")
        self.logs_text.see(tk.END)
        self.logs_text.config(state=tk.DISABLED)

    def run_pipeline_thread(self):
        self.log_message("--- Iniciando Pipeline ---")
        self.run_button.config(state=tk.DISABLED)
        self.save_config_file()
        self.save_data_files()

        # Limpa logs anteriores
        self.logs_text.config(state=tk.NORMAL)
        self.logs_text.delete("1.0", tk.END)
        self.logs_text.config(state=tk.DISABLED)

        thread = threading.Thread(target=self._execute_pipeline_subprocess, daemon=True)
        thread.start()

    def _execute_pipeline_subprocess(self):
        try:
            # Determina o interpretador Python a ser usado (o mesmo que está rodando a GUI)
            python_executable = sys.executable # Default

            # Tenta usar o Python do VIRTUAL_ENV se estiver definido, para maior robustez
            venv_path = os.environ.get('VIRTUAL_ENV')
            if venv_path:
                prospective_venv_python = os.path.join(venv_path, 'bin', 'python')
                if os.path.exists(prospective_venv_python):
                    self.log_queue.put(f"INFO: VIRTUAL_ENV detectado. Usando Python do venv: {prospective_venv_python}")
                    python_executable = prospective_venv_python
                else:
                    self.log_queue.put(f"INFO: VIRTUAL_ENV detectado ({venv_path}), mas '{prospective_venv_python}' não encontrado. Usando sys.executable: {sys.executable}")
            else:
                 self.log_queue.put(f"INFO: VIRTUAL_ENV não detectado. Usando sys.executable: {sys.executable}")

            if not python_executable: # Fallback final se tudo falhar
                python_executable = "python3" # Ou "python" dependendo do sistema

            # Comando para executar o módulo src.main
            # É importante estar no diretório BASE_DIR para que `python -m src.main` funcione corretamente
            # se src.main depender de caminhos relativos ao diretório de trabalho atual para arquivos não gerenciados por BASE_DIR.
            # No nosso caso, src/main.py já usa BASE_DIR, então o cwd do subprocesso é menos crítico,
            # mas é uma boa prática.
            process = subprocess.Popen(
                [python_executable, "-u", "-m", "src.main"], # Adicionada a flag -u
                cwd=BASE_DIR, # Executa a partir do diretório raiz do projeto
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                bufsize=1  # Line-buffered
            )

            # Lidar com stdout
            for line in iter(process.stdout.readline, ''):
                self.log_queue.put(line)
            process.stdout.close()

            # Lidar com stderr
            for line in iter(process.stderr.readline, ''):
                self.log_queue.put(f"ERRO: {line}") # Adiciona prefixo para erros
            process.stderr.close()

            process.wait()
            if process.returncode == 0:
                self.log_queue.put("--- Pipeline concluída com sucesso! ---")
            else:
                self.log_queue.put(f"--- Pipeline concluída com erro (código: {process.returncode}) ---")

        except FileNotFoundError:
            self.log_queue.put(f"ERRO: O interpretador Python '{python_executable}' ou o script não foi encontrado. Verifique a instalação e o PATH.")
        except Exception as e:
            self.log_queue.put(f"Erro ao executar a pipeline: {e}")
        finally:
            self.log_queue.put(None) # Sinal para reabilitar o botão

    def process_log_queue(self):
        try:
            while True:
                message = self.log_queue.get_nowait()
                if message is None: # Sinal para reabilitar botão
                    self.run_button.config(state=tk.NORMAL)
                    break
                self.log_message(message.strip())
        except queue.Empty:
            pass
        self.master.after(100, self.process_log_queue)


if __name__ == "__main__":
    root = tk.Tk()
    gui = PipelineGUI(root)
    root.mainloop()
