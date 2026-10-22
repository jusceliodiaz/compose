-- Script para Restaurar Resolucao 4K UHD e Liberar Passes no Corona
(
    -- 1. Restaura a Janela de Render (VFB) para abrir sempre
    rendShowVFB = true
    setSilentMode false
    
    -- 2. Restaura Resolucao 4K UHD (3840 x 2160 - 16:9)
    renderWidth = 3840
    renderHeight = 2160
    renderPixelAspect = 1.0
    
    local r = renderers.current
    
    -- 3. Desativa regioes de corte ou resolucao travada
    try (r.system_vfbRegions_enabled = false) catch ()
    
    -- 4. Libera os limites de renderizacao:
    -- timeLimit = 0 (sem limite de tempo)
    -- targetError = 0 (nao para sozinho por ruido, limpa de verdade)
    -- passLimit = 0 (deixa renderizar livre ate voce pausar, ou mude para 100)
    try (
        r.progressive_timeLimit = 0
        r.adaptivity_targetError = 0.0
        r.progressive_passLimit = 0
    ) catch ()
    
    -- 5. Reseta a posicao da janela caso esteja escondida
    try (CoronaRenderer.CoronaFp.resetVfbPosition()) catch ()
    try (CoronaRenderer.CoronaFp.showVfb()) catch ()
    
    messageBox "Configuracoes Restauradas com Sucesso!\n\n1. Resolucao: 3840 x 2160 (4K UHD)\n2. Janela VFB: Reativada\n3. Passes: Liberados (sem travas de tempo ou ruido precoce)" title:"Restauracao 4K Corona"
)
