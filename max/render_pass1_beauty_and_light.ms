-- Render 1: Beleza e Luz (Passes de Shading + LightMix)
-- Desativa temporariamente UV e Máscaras (que são renderizados no Render 2 sem filtro/denoise)
(
    local reMgr = maxOps.GetCurRenderElementMgr()
    local reCount = reMgr.NumRenderElements()
    
    for i = 0 to (reCount - 1) do (
        local elem = reMgr.GetRenderElement i
        if elem.elementName == "uv" or elem.elementName == "masks_a" or elem.elementName == "masks_b" then (
            elem.enabled = false
        ) else (
            elem.enabled = true
        )
    )
    
    format "Render 1 configurado: Elementos de Shading e Luz ativados. UV e Máscaras desativados.\n"
    format "Iniciando Render 1...\n"
    
    -- Dispara o render da câmera Corona Camera001
    local cam = getNodeByName "Corona Camera001"
    if cam != undefined then (
        max quick render
    ) else (
        format "ERRO: Corona Camera001 não encontrada!\n"
    )
)
