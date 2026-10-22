-- Render 2: Dados Técnicos (UV Pass e Máscaras)
-- Usa filtro mínimo, 16 passes e sem denoise para manter os pixels nítidos sem borrado
(
    local r = renderers.current
    local reMgr = maxOps.GetCurRenderElementMgr()
    local reCount = reMgr.NumRenderElements()
    
    -- 1. Desativa elementos de shading e luz, ativa APENAS uv e máscaras
    for i = 0 to (reCount - 1) do (
        local elem = reMgr.GetRenderElement i
        if elem.elementName == "uv" or elem.elementName == "masks_a" or elem.elementName == "masks_b" then (
            elem.enabled = true
        ) else (
            elem.enabled = false
        )
    )
    
    -- 2. Configura passes baixos (16 passes são mais que suficientes para UV e máscaras)
    local oldPassLimit = r.progressive_passLimit
    local oldFilterWidth = try(r.image_prefilter_width) catch(2.0)
    
    r.progressive_passLimit = 16
    try (r.image_prefilter_width = 1.0) catch ()
    
    format "Render 2 configurado: Apenas UV e Máscaras ativados (16 passes, filtro reduzido).\n"
    format "Iniciando Render 2...\n"
    
    -- Dispara render
    max quick render
    
    -- 3. Restaura limites originais após render
    r.progressive_passLimit = oldPassLimit
    try (r.image_prefilter_width = oldFilterWidth) catch ()
    format "Limites de render restaurados para o estado original.\n"
)
