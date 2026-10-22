-- Pipeline Completo de Render para ZYcompose (Render 1 seguido de Render 2)
(
    local r = renderers.current
    local reMgr = maxOps.GetCurRenderElementMgr()
    local reCount = reMgr.NumRenderElements()
    local cam = getNodeByName "Corona Camera001"
    
    if cam == undefined do (
        messageBox "Erro: Corona Camera001 não encontrada!" title:"ZYcompose Pipeline"
        return false
    )
    
    -- Salva configurações originais para restaurar no fim
    local origPassLimit = r.progressive_passLimit
    local origTimeLimit = r.progressive_timeLimit
    local origNoiseLimit = r.adaptivity_targetError
    local origFilterWidth = try(r.image_prefilter_width) catch(2.0)
    
    format "\n======================================================\n"
    format ">>> INICIANDO PIPELINE ZYCOMPOSE: RENDER 1 DE 2 <<<\n"
    format "======================================================\n"
    
    -- ----------------------------------------------------
    -- FASE 1: RENDER 1 — BELEZA E LUZ (Shading & LightMix)
    -- ----------------------------------------------------
    -- Ativa passes de luz/shading e desativa UV/Máscaras
    for i = 0 to (reCount - 1) do (
        local elem = reMgr.GetRenderElement i
        if elem.elementName == "uv" or elem.elementName == "masks_a" or elem.elementName == "masks_b" then (
            elem.enabled = false
        ) else (
            elem.enabled = true
        )
    )
    
    -- Qualidade do Render 1: 60 passes (alta qualidade com denoise Corona)
    r.progressive_passLimit = 60
    r.progressive_timeLimit = 0
    r.adaptivity_targetError = 0.0
    try (r.image_prefilter_width = origFilterWidth) catch ()
    
    format "Render 1 configurado para 60 passes com Denoiser ativado.\n"
    format "Renderizando Render 1 agora...\n"
    
    -- Renderiza e salva beauty + elementos de luz
    render camera:cam frame:0 vfb:true
    
    format "\n>>> RENDER 1 CONCLUÍDO COM SUCESSO! <<<\n\n"
    
    -- ----------------------------------------------------
    -- FASE 2: RENDER 2 — DADOS TÉCNICOS (UV & Máscaras)
    -- ----------------------------------------------------
    format "======================================================\n"
    format ">>> INICIANDO PIPELINE ZYCOMPOSE: RENDER 2 DE 2 <<<\n"
    format "======================================================\n"
    
    -- Desativa passes de luz e ativa APENAS UV e Máscaras
    for i = 0 to (reCount - 1) do (
        local elem = reMgr.GetRenderElement i
        if elem.elementName == "uv" or elem.elementName == "masks_a" or elem.elementName == "masks_b" then (
            elem.enabled = true
        ) else (
            elem.enabled = false
        )
    )
    
    -- Qualidade do Render 2: apenas 16 passes são necessários (sem ruído e sem denoise)
    r.progressive_passLimit = 16
    r.progressive_timeLimit = 0
    r.adaptivity_targetError = 0.0
    try (r.image_prefilter_width = 1.0) catch ()
    
    format "Render 2 configurado para 16 passes com filtro nítido.\n"
    format "Renderizando Render 2 agora...\n"
    
    render camera:cam frame:0 vfb:true
    
    format "\n>>> RENDER 2 CONCLUÍDO COM SUCESSO! <<<\n\n"
    
    -- ----------------------------------------------------
    -- FASE 3: RESTAURAÇÃO
    -- ----------------------------------------------------
    r.progressive_passLimit = origPassLimit
    r.progressive_timeLimit = origTimeLimit
    r.adaptivity_targetError = origNoiseLimit
    try (r.image_prefilter_width = origFilterWidth) catch ()
    
    -- Reativa todos os elementos
    for i = 0 to (reCount - 1) do (
        local elem = reMgr.GetRenderElement i
        elem.enabled = true
    )
    
    format "======================================================\n"
    format ">>> PIPELINE COMPLETO FINALIZADO! <<<\n"
    format "Todos os arquivos EXR foram gravados com sucesso em:\n"
    format "C:\\Users\\saant\\Desktop\\compose\\renders\\cam1\\\n"
    format "======================================================\n"
    
    "ALL_RENDERS_FINISHED"
)
