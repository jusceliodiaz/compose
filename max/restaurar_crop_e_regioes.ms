-- Script para Reativar Crop e Regioes no Corona VFB
(
    -- 1. Reativa as Regioes e a ferramenta de Crop no Corona VFB
    try (renderers.current.system_vfbRegions_enabled = true) catch ()
    
    -- 2. Restaura o modo de render padrao caso esteja travado
    try (setRenderType #view) catch ()
    
    messageBox "Crop e Regioes do Corona VFB reativados com sucesso!\nVoce ja pode desenhar caixas de regiao e crop normalmente." title:"Corona Crop / Region"
)
