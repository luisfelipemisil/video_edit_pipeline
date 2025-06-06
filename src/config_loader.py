# -*- coding: utf-8 -*-
import os
import json

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
                config_padrao.update(config_carregada)

                # Ensure sub-structures are dictionaries and have expected keys, handling old formats
                if isinstance(config_padrao.get("generate_edit_from_beats"), bool): # Converte formato antigo
                    config_padrao["generate_edit_from_beats"] = {"enabled": config_padrao["generate_edit_from_beats"], "min_scene_duration_seconds": 2.0, "use_scenes": False}
                elif not isinstance(config_padrao.get("generate_edit_from_beats"), dict): # Se não for bool nem dict, reseta
                    config_padrao["generate_edit_from_beats"] = {"enabled": False, "min_scene_duration_seconds": 2.0, "use_scenes": False}
                else: # Garante que a nova chave use_scenes exista se generate_edit_from_beats for um dict
                    if "use_scenes" not in config_padrao["generate_edit_from_beats"]:
                        config_padrao["generate_edit_from_beats"]["use_scenes"] = False

                if isinstance(config_padrao.get("filtrar_batidas_por_amplitude"), bool):
                     config_padrao["filtrar_batidas_por_amplitude"] = {"enabled": config_padrao["filtrar_batidas_por_amplitude"], "min_amplitude_percentage": 75}
                elif not isinstance(config_padrao.get("filtrar_batidas_por_amplitude"), dict):
                     config_padrao["filtrar_batidas_por_amplitude"] = {"enabled": True, "min_amplitude_percentage": 75}
                
                if not isinstance(config_padrao.get("detectar_cortes_de_cena_video"), dict):
                    config_padrao["detectar_cortes_de_cena_video"] = {"enabled": True, "video_source_index": 0, "threshold": 27.0}
                    
                if not isinstance(config_padrao.get("output_qualities"), list):
                    config_padrao["output_qualities"] = [{"name": "default", "crf": 23}] 
                
                if "movie_name" not in config_padrao: 
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