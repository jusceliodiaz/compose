-- ==============================================================================
-- PORSCHE 360° CAR CONFIGURATOR - RENDER PIPELINE (V2 - ULTRA STABLE)
-- Arquivo: max/render_porsche.ms
--
-- Pintura metalica com flakes: mais dois renders por vista, so o beauty, com a cor
-- da tinta (CoronaColor da camada base) em BRANCO e em PRETO -> paint_white.exr e
-- paint_black.exr. Flakes (glossiness/bump), verniz e luz nao dependem da cor, entao
-- a web troca a cor exata com: pixel(c) = preto + c * (branco - preto).
-- ==============================================================================

global porscheRenderRollout
try (destroyDialog porscheRenderRollout) catch ()

-- Funcao: Configurar IDs e Render Elements de forma segura (sem recriar se ja existirem)
fn setupPorscheIdsAndElements =
(
    format "\n[Porsche Pipeline] Verificando Object IDs e Render Elements...\n"
    
    -- 1. IDs da Carroceria (ID 1) + UVW Map Canal 2
    local bodyObjs = #("body_08_body_0", "body_14_body_0", "body_05_body_0", "body_03_body_0", "body_09_body_0")
    for n in bodyObjs do (
        local o = getNodeByName n
        if o != undefined do (
            o.gbufferChannel = 1
            local hasUvw = false
            for m in o.modifiers where (classof m == Uvwmap and m.mapchannel == 2) do hasUvw = true
            if not hasUvw do (
                local uvMod = Uvwmap()
                uvMod.name = "UV_config"
                uvMod.mapchannel = 2
                uvMod.maptype = 4 -- Box
                uvMod.length = 6000.0
                uvMod.width = 6000.0
                uvMod.height = 6000.0
                addModifier o uvMod
            )
        )
    )
    
    -- 2. IDs das Rodas (ID 2) - apenas o aro/raios das rodas (silver_06_silver_0)
    -- Garante que partes pretas da carroceria, disco de freio, emblema Porsche e frisos nao entrem na mascara
    for n in #("black_shiny_03_black_shiny_0", "silver_d_05_silver_d_0", "logo_04_Newlogo_0", "silver_06_trim") do (
        local o = getNodeByName n
        if o != undefined do o.gbufferChannel = 0
    )
    local wheelRims = #("silver_06_silver_0")
    for n in wheelRims do (
        local o = getNodeByName n
        if o != undefined do (
            o.gbufferChannel = 2
            local hasUvw = false
            for m in o.modifiers where (classof m == Uvwmap and m.mapchannel == 2) do hasUvw = true
            if not hasUvw do (
                local uvMod = Uvwmap name:"UV_config" mapchannel:2 maptype:4 length:6000.0 width:6000.0 height:6000.0
                addModifier o uvMod
            )
        )
    )
    
    -- 3. IDs das Pincas (ID 3)
    local caliperObjs = #("brake_calipers_grey_01_brake_calipers_grey_0", "brake_calipers_grey_02_brake_calipers_grey_0",
                          "brake_calipers_grey_03_brake_calipers_grey_0", "brake_calipers_grey_04_brake_calipers_grey_0")
    for n in caliperObjs do (
        local o = getNodeByName n
        if o != undefined do o.gbufferChannel = 3
    )
    
    -- 3b. ID e UV do Piso / Studio Floor (ID 4)
    local floorObj = getNodeByName "Sphere001"
    if floorObj != undefined do (
        floorObj.gbufferChannel = 4
        local hasUvw = false
        for m in floorObj.modifiers where (classof m == Uvwmap and m.mapchannel == 2) do hasUvw = true
        if not hasUvw do (
            local uvMod = Uvwmap name:"UV_config" mapchannel:2 maptype:4 length:10000.0 width:10000.0 height:10000.0
            addModifier floorObj uvMod
        )
    )
    
    -- 4. Corona Render Elements (so cria se faltar algum)
    local re = maxOps.GetCurRenderElementMgr()
    local existing = #()
    for i = 0 to (re.NumRenderElements()-1) do (
        local el = re.GetRenderElement i
        append existing el.elementName
    )
    
    local needed = #("diff_light", "diff_color", "reflect", "refract", "uv", "masks_a", "masks_b", "masks_c", "masks_floor", "masks_car", "zdepth")
    local needRebuild = false
    for n in needed where (findItem existing n == 0) do needRebuild = true
    
    if needRebuild do (
        re.RemoveAllRenderElements()
        
        local diffLight = CShading_RawComponent()
        diffLight.elementName = "diff_light"
        diffLight.which = 0
        diffLight.useDenoise = true
        re.AddRenderElement diffLight
        
        local diffColor = CShading_SourceColor()
        diffColor.elementName = "diff_color"
        diffColor.which = 0
        re.AddRenderElement diffColor
        
        local reflectEl = CShading_Components()
        reflectEl.elementName = "reflect"
        reflectEl.addDirectDiffuse = false; reflectEl.addDirectReflect = true; reflectEl.addDirectRefract = false
        reflectEl.addDirectTranslucency = false; reflectEl.addIndirectDiffuse = false; reflectEl.addIndirectReflect = true
        reflectEl.addIndirectRefract = false; reflectEl.addIndirectTranslucency = false; reflectEl.addEmission = false
        reflectEl.addDirectVolumetrics = false; reflectEl.addIndirectVolumetrics = false
        reflectEl.useDenoise = true
        re.AddRenderElement reflectEl
        
        local refractEl = CShading_Components()
        refractEl.elementName = "refract"
        refractEl.addDirectDiffuse = false; refractEl.addDirectReflect = false; refractEl.addDirectRefract = true
        refractEl.addDirectTranslucency = false; refractEl.addIndirectDiffuse = false; refractEl.addIndirectReflect = false
        refractEl.addIndirectRefract = true; refractEl.addIndirectTranslucency = false; refractEl.addEmission = false
        refractEl.addDirectVolumetrics = false; refractEl.addIndirectVolumetrics = false
        refractEl.useDenoise = true
        re.AddRenderElement refractEl
        
        local uvEl = CGeometry_UvwCoords()
        uvEl.elementName = "uv"
        uvEl.uvwChannel = 2
        re.AddRenderElement uvEl
        
        local maskA = CMasking_Mask()
        maskA.elementName = "masks_a"
        maskA.mode = 0; maskA.objectMono = 1; maskA.objectMonoOn = true; maskA.propagated = true
        re.AddRenderElement maskA
        
        local maskB = CMasking_Mask()
        maskB.elementName = "masks_b"
        maskB.mode = 0; maskB.objectMono = 2; maskB.objectMonoOn = true; maskB.propagated = true
        re.AddRenderElement maskB
        
        local maskC = CMasking_Mask()
        maskC.elementName = "masks_c"
        maskC.mode = 0; maskC.objectMono = 3; maskC.objectMonoOn = true; maskC.propagated = true
        re.AddRenderElement maskC
        
        -- Mascara do Piso / Chao (ID 4)
        local maskFloor = CMasking_Mask()
        maskFloor.elementName = "masks_floor"
        maskFloor.mode = 0; maskFloor.objectMono = 4; maskFloor.objectMonoOn = true; maskFloor.propagated = true
        re.AddRenderElement maskFloor
        
        -- Mascara do Carro Inteiro (Isola todos os 150 componentes do carro de tudo)
        local maskCar = CMasking_Mask()
        maskCar.elementName = "masks_car"
        maskCar.mode = 2
        local sp = getNodeByName "Sphere001"
        if sp != undefined do maskCar.nodesMono = #(sp)
        maskCar.nodesMonoOn = true
        maskCar.nodesMonoIncludeMod = false -- Exclui o chao -> 100% Carro
        maskCar.propagated = true
        re.AddRenderElement maskCar
        
        local zEl = CGeometry_ZDepth()
        zEl.elementName = "zdepth"
        zEl.minZ = 2000.0; zEl.maxZ = 12000.0
        re.AddRenderElement zEl
    )
    
    -- 5. Garantir Timeline 0 a 72 frames (5 graus por frame)
    if animationRange.end != 72f do (
        animationRange = interval 0f 72f
        local cam = getNodeByName "Corona Camera001"
        if cam != undefined and (classof cam.pos.controller == Path_Constraint) do (
            local pc = cam.pos.controller
            deleteKeys pc.percent.controller #allKeys
            with animate on (
                at time 0f pc.percent = 0.0
                at time 72f pc.percent = 100.0
            )
        )
    )
    
    format "[Porsche Pipeline] OK! % elementos ativos (0 a 72 frames).\n" (re.NumRenderElements())
    true
)

-- Funcao: Renderizar 1 Frame especifico
fn renderPorscheFrame frameNum passCount outBaseDir width:1920 height:1080 showVfb:false =
(
    local cam = getNodeByName "Corona Camera001"
    if cam == undefined do (
        messageBox "Corona Camera001 nao encontrada!" title:"Erro"
        return false
    )
    
    local r = renderers.current
    local reMgr = maxOps.GetCurRenderElementMgr()
    local frameStr = formattedPrint frameNum format:"03d"
    local frameFolder = outBaseDir + "frame_" + frameStr + @"\"
    makeDir frameFolder all:true
    
    -- Configura caminhos dos arquivos de cada elemento
    for i = 0 to (reMgr.NumRenderElements()-1) do (
        local el = reMgr.GetRenderElement i
        reMgr.SetRenderElementFilename i (frameFolder + el.elementName + ".exr")
    )
    
    r.progressive_passLimit = passCount
    r.progressive_timeLimit = 0
    r.system_vfbRegions_enabled = false
    renderWidth = width
    renderHeight = height
    renderPixelAspect = 1.0
    rendSaveFile = true
    rendOutputFilename = frameFolder + "beauty.exr"
    
    sliderTime = frameNum
    
    format ">>> Renderizando Frame % (Passes: %, Res: %x%)...\n" frameNum passCount width height
    
    -- Garante que a pasta existe imediatamente antes de salvar
    makeDir frameFolder all:true
    
    local renderOk = true
    try (
        render camera:cam frame:frameNum outputfile:(frameFolder + "beauty.exr") vfb:showVfb cancelled:&wasCancelled
        if wasCancelled do renderOk = false
    ) catch (
        format ">>> Render cancelado ou erro no Frame %: %\n" frameNum (getCurrentException())
        renderOk = false
    )
    
    if not renderOk do return false
    
    format ">>> Frame % salvo em %\n" frameNum frameFolder
    true
)

-- Funcao: CoronaColor das tintas da carroceria (ID 1): cor da camada base, usada
-- no difuso e no reflexo metalico (falloff). Devolve os mapas unicos.
fn getPorschePaintColorMaps =
(
    local maps = #()
    for o in objects where o.gbufferChannel == 1 and o.material != undefined do (
        local base = try o.material.baseMtl catch undefined
        if base != undefined do (
            local d = try base.texmapDiffuse catch undefined
            if classof d == CoronaColor do appendIfUnique maps d
            local r0 = try base.texmapReflect catch undefined
            if classof r0 == CoronaColor do appendIfUnique maps r0
            local r1 = try base.texmapReflect.map1 catch undefined
            if classof r1 == CoronaColor do appendIfUnique maps r1
        )
        local l1 = try o.material.layers[1] catch undefined
        if l1 != undefined do (
            local lr = try l1.texmapReflect catch undefined
            if classof lr == CoronaColor do appendIfUnique maps lr
        )
    )
    maps
)

-- Funcao: Renderizar os passes de pintura (paint_white / paint_black) de 1 frame.
-- Mesma camera, resolucao, passes e denoiser do beauty; render elements desligados.
fn renderPorschePaintPasses frameNum passCount outBaseDir width:1920 height:1080 showVfb:false =
(
    local cam = getNodeByName "Corona Camera001"
    if cam == undefined do (
        messageBox "Corona Camera001 nao encontrada!" title:"Erro"
        return false
    )
    local maps = getPorschePaintColorMaps()
    if maps.count == 0 do (
        messageBox "Nenhuma tinta com CoronaColor na carroceria (Object ID 1).\nRode o passo 1 antes." title:"Erro"
        return false
    )
    local saved = for mp in maps collect #(mp.color, mp.method, mp.multiplier)
    local r = renderers.current
    local reMgr = maxOps.GetCurRenderElementMgr()
    local elementsWereOn = reMgr.GetElementsActive()
    local frameStr = formattedPrint frameNum format:"03d"
    local frameFolder = outBaseDir + "frame_" + frameStr + @"\"
    makeDir frameFolder all:true

    r.progressive_passLimit = passCount
    r.progressive_timeLimit = 0
    r.system_vfbRegions_enabled = false
    renderWidth = width
    renderHeight = height
    renderPixelAspect = 1.0
    sliderTime = frameNum

    local ok = true
    try (
        reMgr.SetElementsActive false
        for pass in #(#("paint_white", white), #("paint_black", black)) do (
            for mp in maps do (
                mp.method = 0
                mp.multiplier = 1.0
                mp.color = pass[2]
            )
            local outFile = frameFolder + pass[1] + ".exr"
            format ">>> Pintura % (% tintas) -> %\n" pass[1] maps.count outFile
            render camera:cam frame:frameNum outputfile:outFile vfb:showVfb
            windows.processPostedMessages()
        )
    ) catch (
        ok = false
        format ">>> ERRO nos passes de pintura: %\n" (getCurrentException())
    )
    -- restaura sempre as cores originais e os render elements
    for i = 1 to maps.count do (
        maps[i].color = saved[i][1]
        maps[i].method = saved[i][2]
        maps[i].multiplier = saved[i][3]
    )
    reMgr.SetElementsActive elementsWereOn
    if ok do format ">>> Passes de pintura do frame % salvos em %\n" frameNum frameFolder
    gc light:true
    ok
)

-- Funcao: Renderizar Loop 360 com seguranca e estabilidade (sem GC/processPostedMessages no loop para evitar Access Violation)
fn renderPorsche360 startF endF passCount outBaseDir width:1920 height:1080 withPaint:false skipExisting:true =
(
    local startTime = timeStamp()
    local totalFrames = (endF - startF + 1)
    local currentIdx = 0
    
    format "\n==============================================================\n"
    format ">>> INICIANDO RENDER 360 SPIN PORSCHE: % frames (% a %)\n" totalFrames startF endF
    format "==============================================================\n"
    
    for f = startF to endF do (
        currentIdx += 1
        local frameStr = formattedPrint f format:"03d"
        local frameFolder = outBaseDir + "frame_" + frameStr + @"\"
        local existingExrs = getFiles (frameFolder + "*.exr")
        
        local hasBase = existingExrs.count >= 10
        local hasPaint = (doesFileExist (frameFolder + "paint_white.exr")) and (doesFileExist (frameFolder + "paint_black.exr"))
        
        if skipExisting and hasBase and ((not withPaint) or hasPaint) then (
            format "[Progresso: % de %] Frame % ja completo (% EXRs) - pulando.\n" currentIdx totalFrames f existingExrs.count
        ) else (
            format "\n[Progresso: % de %] Frame %...\n" currentIdx totalFrames f
            local ok = true
            if (not skipExisting) or (not hasBase) do (
                ok = renderPorscheFrame f passCount outBaseDir width:width height:height showVfb:false
            )
            if ok and withPaint and ((not skipExisting) or (not hasPaint)) do (
                ok = renderPorschePaintPasses f passCount outBaseDir width:width height:height showVfb:false
            )
            if not ok do (
                format ">>> Render interrompido no Frame %!\n" f
                return false
            )
        )
    )
    
    local elapsedSec = (timeStamp() - startTime) / 1000.0
    local elapsedMin = elapsedSec / 60.0
    format "\n==============================================================\n"
    format ">>> SPIN 360 CONCLUIDO! Tempo total: % min\n" elapsedMin
    format "==============================================================\n"
    
    messageBox ("Render 360 concluido com sucesso!\nTempo: " + (elapsedMin as string) + " min\nPasta: " + outBaseDir) title:"Porsche 360 Render"
    true
)

-- Rollout UI
rollout porscheRenderRollout "Porsche 360 - Render Pipeline" width:380 height:565
(
    group "Configuracao de Saida"
    (
        edittext edtPath "Pasta:" text:@"C:\Users\saant\Desktop\configurador_carro\renders\porsche_4k_v2\" width:340 labelOnTop:true
        button btnBrowse "Procurar Pasta..." width:120 align:#right
    )
    
    group "Parametros de Render"
    (
        spinner spnPasses "Limite de Passes:" range:[5, 200, 15] type:#integer fieldWidth:50 tooltip:"15 passes recomendados para estúdio com Denoiser"
        spinner spnWidth "Largura (px):" range:[480, 7680, 3840] type:#integer fieldWidth:50
        spinner spnHeight "Altura (px):" range:[270, 4320, 2160] type:#integer fieldWidth:50
    )
    
    group "Faixa de Frames (360 - 72 Vistas)"
    (
        spinner spnTestFrame "Frame de Teste:" range:[0, 72, 0] type:#integer fieldWidth:50
        spinner spnStartFrame "Frame Inicial:" range:[0, 72, 0] type:#integer fieldWidth:50
        spinner spnEndFrame "Frame Final:" range:[0, 72, 71] type:#integer fieldWidth:50
        label lblTip "Total: 72 vistas unicas (0 a 71 = 5 graus/frame)" align:#left
    )
    
    group "Acoes"
    (
        button btnSetup "1. Verificar IDs e Render Elements" width:340 height:30
        button btnRenderTest "2. Renderizar Frame Unico (Teste)" width:340 height:32
        button btnRenderPaint "2b. Passes de Pintura do Frame de Teste" width:340 height:30 tooltip:"Beauty com a tinta da carroceria em branco e em preto (paint_white/paint_black.exr): pintura metalica com flakes na web"
        checkbox chkSkip "Pular frames ja prontos (retomar de onde parou)" checked:true
        checkbox chkPaint "Incluir passes de pintura no 360 (3 renders/frame)" checked:true
        button btnRender360 "3. Renderizar Spin 360 (Faixa Selecionada)" width:340 height:40
    )
    
    on btnBrowse pressed do (
        local dir = getSavePath caption:"Selecione a Pasta de Saida" initialDir:edtPath.text
        if dir != undefined do (
            if not (matchPattern dir pattern:@"*\") do dir += @"\"
            edtPath.text = dir
        )
    )
    
    on btnSetup pressed do (
        setupPorscheIdsAndElements()
        messageBox "Tudo verificado e pronto para renderizar!" title:"Sucesso"
    )
    
    on btnRenderTest pressed do (
        setupPorscheIdsAndElements()
        renderPorscheFrame spnTestFrame.value spnPasses.value edtPath.text width:spnWidth.value height:spnHeight.value showVfb:true
    )
    
    on btnRenderPaint pressed do (
        setupPorscheIdsAndElements()
        renderPorschePaintPasses spnTestFrame.value spnPasses.value edtPath.text width:spnWidth.value height:spnHeight.value showVfb:true
    )

    on btnRender360 pressed do (
        setupPorscheIdsAndElements()
        renderPorsche360 spnStartFrame.value spnEndFrame.value spnPasses.value edtPath.text width:spnWidth.value height:spnHeight.value withPaint:chkPaint.checked skipExisting:chkSkip.checked
    )
)

createDialog porscheRenderRollout
