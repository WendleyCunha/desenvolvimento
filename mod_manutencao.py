import pandas as pd
import os

def processar_dados_diarios(caminho_arquivo):
    """
    Lê a planilha, limpa os nomes das colunas e prepara os dados para o Dash 360.
    """
    try:
        # Detecta se é Excel ou CSV e lê com encoding corrigido
        if caminho_arquivo.endswith('.csv'):
            df = pd.read_csv(caminho_arquivo, sep=';', encoding='latin1')
        else:
            df = pd.read_excel(caminho_arquivo)

        # 1. TRATAMENTO DE COLUNAS (Resolvendo o problema do 'Ã£')
        # Mapeamento manual para garantir que o Python entenda exatamente o que é cada coluna
        colunas_corrigidas = {
            'Dt EmissÃ£o': 'dt_emissao',
            'Dt Age': 'dt_agendamento',
            'Data Lib': 'dt_liberacao',
            'Data Prev': 'dt_previsao',
            'Data Ent': 'dt_entrega',
            'OrÃ§amento': 'orcamento',
            'Tipo Venda': 'tipo_venda',
            'Valor Venda': 'valor_venda'
        }
        df.rename(columns=colunas_corrigidas, inplace=True)

        # 2. CONVERSÃO DE DATAS
        # Isso permite que você filtre por "Vendas de Sexta a Domingo" facilmente
        colunas_data = ['dt_emissao', 'dt_agendamento', 'dt_liberacao', 'dt_previsao', 'dt_entrega']
        for col in colunas_data:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')

        # 3. CRIAÇÃO DE REGRAS (Exemplos para o Dash 360)
        
        # Regra A: Lucro Bruto e Margem
        df['lucro'] = df['valor_venda'] - df['Custo']
        df['margem_percentual'] = (df['lucro'] / df['valor_venda']) * 100

        # Regra B: Status de Entrega (Atrasado ou No Prazo)
        df['status_logistica'] = df.apply(
            lambda x: 'Atrasado' if x['dt_entrega'] > x['dt_previsao'] else 'No Prazo', 
            axis=1
        )

        # Regra C: Identificador de Dia da Semana (Para tratar o acúmulo de fds)
        df['dia_semana_nome'] = df['dt_emissao'].dt.day_name() # 'Friday', 'Saturday', etc.

        return df

    except Exception as e:
        return f"Erro ao processar arquivo: {e}"

def consolidar_final_de_semana(df):
    """
    Regra específica para agrupar dados de Sex/Sab/Dom se necessário.
    """
    # Exemplo: Marcar vendas que entram no "bolo" da segunda-feira
    dias_fds = ['Friday', 'Saturday', 'Sunday']
    df['venda_fds'] = df['dia_semana_nome'].isin(dias_fds)
    return df
