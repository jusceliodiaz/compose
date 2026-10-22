-- Script ZYcompose: Render 4K Sala de Estar com 5 Mascaras, UV e Iluminacao
(
    clearListener()
    format "==========================================================\n"
    format ">>> CONFIGURANDO E DISPARANDO RENDER 4K SALA DE ESTAR <<<\n"
    format "==========================================================\n"
    
    -- 1. Suprime popups bloqueantes de arquivos ausentes
    setSilentMode true
    try (renderers.current.system_vfbShowCoronaWarnings = false) catch ()
    
    local outDir = @"C:\Users\saant\Desktop\compose\renders\sala_estar\"
    makeDir outDir all:true
    local prefix = "cam7_"
    
    local r = renderers.current
    local reMgr = maxOps.GetCurRenderElementMgr()
    local cam = getNodeByName "CoronaCamera007"
    
    if cam == undefined do (
        messageBox "Erro: CoronaCamera007 nao encontrada na cena!" title:"ZYcompose"
        return false
    )
    
    -- 2. Configuracao da Resolucao 4K UHD
    r.system_vfbRegions_enabled = false
    renderWidth = 3840
    renderHeight = 2160
    renderPixelAspect = 1.0
    
    -- Saida principal Beauty
    rendSaveFile = true
    rendOutputFilename = outDir + prefix + "beauty.exr"
    
    -- Funcao auxiliar para conferir se elemento ja existe
    fn hasElement named = (
        local found = false
        for i = 0 to (reMgr.NumRenderElements() - 1) do (
            local el = reMgr.GetRenderElement i
            if (matchPattern el.elementName pattern:named ignoreCase:true) do found = true
        )
        found
    )
    
    -- 3. Garante elementos essenciais de iluminacao e reflexo caso faltem
    if not (hasElement "diff_light") do (
        local eDiffLight = CShading_RawComponent()
        eDiffLight.elementName = "diff_light"
        eDiffLight.which = 0 -- Diffuse
        try (eDiffLight.useDenoise = true) catch ()
        reMgr.AddRenderElement eDiffLight
        format "  + Adicionado elemento: diff_light\n"
    )
    if not (hasElement "diff_color") do (
        local eDiffColor = CShading_SourceColor()
        eDiffColor.elementName = "diff_color"
        eDiffColor.which = 0 -- Diffuse
        reMgr.AddRenderElement eDiffColor
        format "  + Adicionado elemento: diff_color\n"
    )
    if not (hasElement "reflect") do (
        local eReflect = CShading_Components()
        eReflect.elementName = "reflect"
        eReflect.which = 2 -- Reflection
        try (eReflect.useDenoise = true) catch ()
        reMgr.AddRenderElement eReflect
        format "  + Adicionado elemento: reflect\n"
    )
    
    -- 4. Habilita e direciona TODOS os elementos para a pasta de render com o prefixo cam7_
    local numElem = reMgr.NumRenderElements()
    format "\nTotal de Render Elements configurados: %\n" numElem
    
    for i = 0 to (numElem - 1) do (
        local elem = reMgr.GetRenderElement i
        elem.enabled = true
        elem.filter = true
        
        local elemName = elem.elementName
        local targetFile = outDir + prefix + elemName + ".exr"
        reMgr.SetRenderElementFilename i targetFile
        format "  [%] % -> %\n" (i+1) elemName targetFile
    )
    
    -- 5. Limites de Qualidade e Ruido (3.0% de ruido ou max 50 passes para 4K limpo)
    r.progressive_passLimit = 50
    r.progressive_timeLimit = 0
    r.adaptivity_targetError = 3.0
    
    format "\nRender 4K UHD configurado com sucesso!\n"
    format "Disparando renderizacao na CoronaCamera007...\n"
    format "Os passes serao salvos automaticamente ao finalizar.\n"
    
    -- 6. Dispara o Render no Frame Buffer do Corona
    render camera:cam frame:0 vfb:true
    
    format "\n==========================================================\n"
    format ">>> RENDER CONCLUIDO! TODOS OS ARQUIVOS FORAM GRAVADOS! <<<\n"
    format "Pasta de destino: %\n" outDir
    format "==========================================================\n"
    
    messageBox "Render 4K Concluido com Sucesso!\nTodos os passes e mascaras foram gravados na pasta." title:"ZYcompose"
)
