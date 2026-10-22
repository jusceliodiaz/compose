-- Pipeline Automatizado de Render 4K para Sala de Estar (CENA_INTERNA_RENDEREASY)
-- Resolução 4K UHD: 3840 x 2160 (Aspect 16:9)
-- 2 Passes: 
--   Render 1: Shading, Beauty e Luz até 4.0% de ruído (máx 50 passes, com Denoiser Corona)
--   Render 2: UVs e Máscaras (16 passes rápidos com filtro 1.0 px sem denoise)
(
    local outDir = @"C:\Users\saant\Desktop\compose\renders\sala_estar\"
    makeDir outDir all:true
    
    local r = renderers.current
    local reMgr = maxOps.GetCurRenderElementMgr()
    local reCount = reMgr.NumRenderElements()
    local cam = getNodeByName "CoronaCamera007"
    
    if cam == undefined do (
        print "ERRO: CoronaCamera007 nao encontrada!"
        return "ERROR_NO_CAMERA"
    )
    
    -- Garante resolução 4K UHD (3840x2160) e desativa regiões
    r.system_vfbRegions_enabled = false
    renderWidth = 3840
    renderHeight = 2160
    renderPixelAspect = 1.0
    rendSaveFile = true
    rendOutputFilename = outDir + "cam7_beauty.exr"
    
    -- Salva parâmetros originais
    local origPassLimit = r.progressive_passLimit
    local origTimeLimit = r.progressive_timeLimit
    local origNoiseLimit = r.adaptivity_targetError
    local origFilterWidth = try(r.image_prefilter_width) catch(2.0)
    
    print "\n======================================================"
    print ">>> INICIANDO PIPELINE SALA DE ESTAR 4K: RENDER 1 DE 2 <<<"
    print "Resolucao: 3840x2160 (16:9 4K UHD)"
    print "Criterio: Ruido <= 4.0% ou max 50 passes"
    print "======================================================"
    
    -- ----------------------------------------------------
    -- FASE 1: RENDER 1 — SHADING, BEAUTY E LUZ (NOISE 4.0%)
    -- ----------------------------------------------------
    for i = 0 to (reCount - 1) do (
        local elem = reMgr.GetRenderElement i
        if matchPattern elem.elementName pattern:"uv*" or matchPattern elem.elementName pattern:"masks*" then (
            elem.enabled = false
        ) else (
            elem.enabled = true
        )
    )
    
    r.progressive_passLimit = 50
    r.progressive_timeLimit = 0
    r.adaptivity_targetError = 4.0
    try (r.image_prefilter_width = origFilterWidth) catch ()
    
    print "Render 1 configurado: Shading + Luz com Denoise."
    print "Renderizando Render 1 agora..."
    
    render camera:cam frame:0 vfb:true
    
    print "\n>>> RENDER 1 CONCLUIDO COM SUCESSO! <<<\n"
    
    -- ----------------------------------------------------
    -- FASE 2: RENDER 2 — DADOS TECNICOS (UV & MASCARAS)
    -- ----------------------------------------------------
    print "======================================================"
    print ">>> INICIANDO PIPELINE SALA DE ESTAR 4K: RENDER 2 DE 2 <<<"
    print "======================================================"
    
    for i = 0 to (reCount - 1) do (
        local elem = reMgr.GetRenderElement i
        if matchPattern elem.elementName pattern:"uv*" or matchPattern elem.elementName pattern:"masks*" then (
            elem.enabled = true
        ) else (
            elem.enabled = false
        )
    )
    
    -- 16 passes para UV e Máscaras (sem ruído, sem denoise, filtro nítido 1.0)
    r.progressive_passLimit = 16
    r.progressive_timeLimit = 0
    r.adaptivity_targetError = 0.0
    try (r.image_prefilter_width = 1.0) catch ()
    
    print "Render 2 configurado: 16 passes com filtro nitido 1.0 px."
    print "Renderizando Render 2 agora..."
    
    render camera:cam frame:0 vfb:true
    
    print "\n>>> RENDER 2 CONCLUIDO COM SUCESSO! <<<\n"
    
    -- ----------------------------------------------------
    -- FASE 3: RESTAURACAO
    -- ----------------------------------------------------
    r.progressive_passLimit = origPassLimit
    r.progressive_timeLimit = origTimeLimit
    r.adaptivity_targetError = origNoiseLimit
    try (r.image_prefilter_width = origFilterWidth) catch ()
    
    for i = 0 to (reCount - 1) do (
        local elem = reMgr.GetRenderElement i
        elem.enabled = true
    )
    
    print "======================================================"
    print ">>> PIPELINE 4K FINALIZADO COM SUCESSO! <<<"
    print "======================================================"
    
    "SALA_ESTAR_4K_RENDER_FINISHED"
)
