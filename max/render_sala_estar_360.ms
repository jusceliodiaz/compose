-- Pipeline Automatizado de Render 360 Panorâmico para Sala de Estar (CoronaCam 360)
-- Proporção 2:1 (Equirectangular 360° x 180°)
(
    clearListener()
    format "==========================================================\n"
    format ">>> CONFIGURANDO RENDER 360 PANORÂMICO SALA DE ESTAR <<<\n"
    format "==========================================================\n"
    
    setSilentMode true
    try (renderers.current.system_vfbShowCoronaWarnings = false) catch ()
    
    local outDir = @"C:\Users\saant\Desktop\compose\renders\sala_360\"
    makeDir outDir all:true
    local prefix = "cam360_"
    
    local r = renderers.current
    local reMgr = maxOps.GetCurRenderElementMgr()
    local cam = getNodeByName "CoronaCamera_360"
    
    if cam == undefined do (
        format "ERRO: CoronaCamera_360 nao encontrada na cena!\n"
        return false
    )
    
    -- Configuração 2:1 Equirretangular (2048x1024 para teste ágil ou 4096x2048 para produção)
    -- Altere para 4096 e 2048 se desejar qualidade final imediata
    local resWidth = 2048
    local resHeight = 1024
    
    r.system_vfbRegions_enabled = false
    renderWidth = resWidth
    renderHeight = resHeight
    renderPixelAspect = 1.0
    
    -- Saída Beauty principal
    rendSaveFile = true
    rendOutputFilename = outDir + prefix + "beauty.exr"
    
    -- Direciona todos os Render Elements para a pasta 360
    local numElem = reMgr.NumRenderElements()
    format "\nTotal de Render Elements a direcionar: %\n" numElem
    
    for i = 0 to (numElem - 1) do (
        local elem = reMgr.GetRenderElement i
        elem.enabled = true
        elem.filter = true
        
        local elemName = elem.elementName
        local targetFile = outDir + prefix + elemName + ".exr"
        reMgr.SetRenderElementFilename i targetFile
        format "  [%] % -> %\n" (i+1) elemName targetFile
    )
    
    -- Limites de qualidade (adaptativo 4.0% ou max 40 passes para teste rápido)
    r.progressive_passLimit = 40
    r.progressive_timeLimit = 0
    r.adaptivity_targetError = 4.0
    
    format "\nRender 360 configurado (%x%)!\n" resWidth resHeight
    format "Disparando renderizacao na CoronaCamera_360...\n"
    
    render camera:cam frame:0 vfb:true
    
    format "\n==========================================================\n"
    format ">>> RENDER 360 CONCLUIDO COM SUCESSO! <<<\n"
    format "Pasta de destino: %\n" outDir
    format "==========================================================\n"
    "RENDER_360_FINISHED"
)
