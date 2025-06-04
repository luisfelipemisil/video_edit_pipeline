# -*- coding: utf-8 -*-
import os

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
        print(f"Erro: Arquivo de referência de amplitudes '{amplitude_file_path}' não encontrado.")
        return amplitude_map, 0.0

    with open(amplitude_file_path, 'r') as f:
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
                print(f"Aviso: Linha ignorada (formato inválido no arquivo de amplitudes): '{linha}'")
                continue
    
    max_amplitude = max(all_amplitudes) if all_amplitudes else 0.0
    return amplitude_map, max_amplitude

def filter_timestamps_by_amplitude(
    timestamps_to_filter_file_path, 
    amplitude_map, 
    overall_max_amplitude
):
    """
    Filtra timestamps de um arquivo especificado (contendo apenas timestamps)
    baseado em suas amplitudes (buscadas no amplitude_map) em relação à overall_max_amplitude.
    """
    if not amplitude_map or overall_max_amplitude == 0:
        print("Aviso: Mapa de amplitudes vazio ou amplitude máxima é zero. Nenhum timestamp será filtrado.")
        return []

    limite_inferior_amplitude = 0.75 * overall_max_amplitude
    filtered_timestamps = []

    if not os.path.exists(timestamps_to_filter_file_path):
        print(f"Erro: Arquivo de timestamps para filtrar '{timestamps_to_filter_file_path}' não encontrado.")
        return filtered_timestamps

    with open(timestamps_to_filter_file_path, 'r') as f:
        for linha in f:
            timestamp = linha.strip()
            if not timestamp:
                continue
            
            beat_amplitude = amplitude_map.get(timestamp)
            
            if beat_amplitude is None:
                # print(f"Aviso: Amplitude não encontrada para o timestamp '{timestamp}'. Será ignorado.")
                continue 
                
            if beat_amplitude >= limite_inferior_amplitude:
                filtered_timestamps.append(timestamp)
            
    return filtered_timestamps

if __name__ == "__main__":
    # Arquivo de referência: contém timestamps e suas amplitudes. Usado para encontrar a MAIOR AMPLITUDE GERAL.
    amplitude_reference_file = "/Users/lfms/Documents/projeto_cut_videos/songs/analise_batidas/beats_with_amplitude.txt" # Exemplo: deve conter amplitudes
    
    # Arquivo de batidas a ser filtrado: contém APENAS TIMESTAMPS.
    # As amplitudes para estes timestamps serão buscadas no arquivo de referência.
    beats_file_to_filter = "/Users/lfms/Documents/projeto_cut_videos/songs/analise_batidas/beats.txt"

    print(f"Analisando amplitudes de: {amplitude_reference_file}...")
    timestamp_to_amplitude_map, overall_max_amplitude = load_amplitude_data(amplitude_reference_file)
    
    if not timestamp_to_amplitude_map:
        print("Não foi possível carregar dados de amplitude do arquivo de referência. Encerrando.")
    else:
        print(f"Maior amplitude geral registrada (de {os.path.basename(amplitude_reference_file)}): {overall_max_amplitude:.2f}")
        print(f"Limite inferior de amplitude para filtro (75%): {0.75 * overall_max_amplitude:.2f}")

        print(f"\nFiltrando timestamps de: {beats_file_to_filter}...")
        final_filtered_timestamps = filter_timestamps_by_amplitude(
            beats_file_to_filter,
            timestamp_to_amplitude_map,
            overall_max_amplitude
        )
        
        print(f"\nBatidas filtradas (timestamps de '{os.path.basename(beats_file_to_filter)}' com amplitude >= 75% da maior geral):")
        if final_filtered_timestamps:
            for ts in final_filtered_timestamps:
                print(ts)
        else:
            print(f"Nenhuma batida de '{os.path.basename(beats_file_to_filter)}' atendeu aos critérios de filtro.")
            print(ts)
    else:
        print("Nenhuma batida com amplitude foi carregada para análise.")