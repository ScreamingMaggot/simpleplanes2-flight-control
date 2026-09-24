-- Global table to store button configurations
buttons = {}
NumButtons = 16
pageId = ""
weaponListChanged = false;
targetNameWidget = nil;
tgpOnWidget = nil;
tgpDistanceWidget = nil;
tgpOffWidget = nil;

local emptyFunction = function() end

-- Function to reset a button to default values
local function resetButton(button)
    button.label = ""
    button.onPress = emptyFunction
    button.onRelease = emptyFunction
    button.onUpdate = emptyFunction
    button.buttonWidget.Flagged = false
    if button.buttonClass ~= nil then
        button.buttonWidget:RemoveClass(button.buttonClass)
        button.buttonClass = nil
    end
end

-- Function to set up buttons with onPress and optional onRelease actions
function setButton(buttonId, label, onPress, onRelease)
    if not buttons[buttonId] then
        buttons[buttonId] = {}
    end

    buttons[buttonId].label = label
    buttons[buttonId].onPress = onPress or emptyFunction
    buttons[buttonId].onRelease = onRelease or emptyFunction
    return buttons[buttonId]
end

-- Function to clear all buttons by resetting them
function clearButtons()
    for i = 1, NumButtons do
        resetButton(buttons[i])
    end
end

-- Function to update button visibility and labels
function updateButtons()
    for i = 1, NumButtons do
        if buttons[i].label ~= "" then
            if buttons[i].buttonText then
                buttons[i].buttonText:SetStyle("text", buttons[i].label)
                buttons[i].buttonWidget.Visible = true
                if buttons[i].buttonClass ~= nil then
                   buttons[i].buttonWidget:AddClass(buttons[i].buttonClass)
                end
            end
        else
            if buttons[i].buttonWidget then
                buttons[i].buttonWidget.Visible = false
            end
        end
    end
end

function setTgpInputs(x, y, z)
    TgpSpeed = 3
    if x ~= 0 then
        craft.Controls:OverrideInput("TargetingPodSlewLeftRight", x * TgpSpeed)
    else
        craft.Controls:ReleaseInput("TargetingPodSlewLeftRight")
    end

    if y ~= 0 then
        craft.Controls:OverrideInput("TargetingPodSlewUpDown", y * TgpSpeed)
    else
        craft.Controls:ReleaseInput("TargetingPodSlewUpDown")
    end

    if z ~= 0 then
        craft.Controls:OverrideInput("TargetingPodZoom", z * TgpSpeed)
    else
        craft.Controls:ReleaseInput("TargetingPodZoom")
    end
end

function resetTgpInputs()
    setTgpInputs(0, 0, 0);
end

function setActivationButton(buttonId, label, group, toggleFunction, updateFunction)
    buttons[buttonId].label = label;
    if group ~= nil then
        buttons[buttonId].onPress = function() craft.Controls:ToggleActivationGroup(group) end;
        buttons[buttonId].onUpdate = function()
            buttons[buttonId].buttonWidget.Flagged = craft.Controls.GetActivationState(group);
        end;
    else
        buttons[buttonId].onPress = toggleFunction;
        buttons[buttonId].onUpdate = updateFunction;
    end
end

function updateWeaponButton(buttonId, weaponId)
    local weapon = craft.Targeting:GetWeaponSystem(weaponId)
    if weapon ~= nil then
        local label = string.format("%s x%d", weapon.Name, weapon.Ammo);
        setButton(buttonId, label, function() craft.Targeting.SelectWeapon(weaponId) end);
        buttons[buttonId].buttonWidget.Flagged = weapon.Selected;
        buttons[buttonId].buttonClass = "wide-button";
    end
end

function buildWeaponsPage()
    clearButtons();
    setButton(1, "MENU", function() mfd.SelectPage("page-menu") end)

    setButton(2, "OFF", function() craft.Targeting.Mode = TargetingSystemMode.Off end)
        .buttonWidget.Flagged = (craft.Targeting.Mode == TargetingSystemMode.Off);
    
    setButton(3, "AIR", function() craft.Targeting.Mode = TargetingSystemMode.AirToAir end)
        .buttonWidget.Flagged = (craft.Targeting.Mode == TargetingSystemMode.AirToAir);

    setButton(4, "GND", function() craft.Targeting.Mode = TargetingSystemMode.AirToGround end)
        .buttonWidget.Flagged = (craft.Targeting.Mode == TargetingSystemMode.AirToGround);

    setButton(9, "►", function() craft.Targeting.NextTarget() end);
    setButton(12, "◄", function() craft.Targeting.PreviousTarget() end);
    
    setButton(7, "CSMR x0", 
        function() craft.Controls.OverrideInput("LaunchCountermeasures", 1.0) end,
        function() craft.Controls.ReleaseInput("LaunchCountermeasures") end);
    buttons[7].buttonClass = "wide-button";

    updateWeaponButton(16, 1);
    updateWeaponButton(15, 2);
    updateWeaponButton(14, 3);

    updateWeaponButton(5, 5);
    updateWeaponButton(6, 6);

    updateButtons();
end

-- Function called when a page is selected
function onPageSelected(id)
    -- Configure buttons for this page
    clearButtons()

    pageId = id;

    if id == "page-menu" then
        setButton(6, "TGP", function() mfd.SelectPage("page-tgp") end)
        setButton(7, "FLT", function() mfd.SelectPage("page-flt") end)
        setButton(15, "ACT", function() mfd.SelectPage("page-act") end)
        setButton(14, "WPN", function() mfd.SelectPage("page-wpn") end)
    elseif id == "page-act" then
        setButton(1, "MENU", function() mfd.SelectPage("page-menu") end)
        
        setActivationButton(16, "AG1", 1, nil, nil);
        setActivationButton(15, "AG2", 2, nil, nil);
        setActivationButton(14, "AG3", 3, nil, nil);
        setActivationButton(13, "AG4", 4, nil, nil);

        setActivationButton(5, "AG5", 5, nil, nil);
        setActivationButton(6, "AG6", 6, nil, nil);
        setActivationButton(7, "AG7", 7, nil, nil);
        setActivationButton(8, "AG8", 8, nil, nil);

        setActivationButton(10, "PARK", nil, function() craft.Controls.ParkingBrake = not craft.Controls.ParkingBrake; end, function()
            buttons[10].buttonWidget.Flagged = craft.Controls.ParkingBrake;
        end)
        setActivationButton(11, "GEAR", nil, function() craft.Controls.LandingGearDown = not craft.Controls.LandingGearDown; end, function()
            buttons[11].buttonWidget.Flagged = craft.Controls.LandingGearDown;
        end)

    elseif id == "page-tgp" then
        setButton(1, "MENU", function() mfd.SelectPage("page-menu") end)

        setButton(6, "▲", function() setTgpInputs(0, 1, 0) end, function() resetTgpInputs() end)
        setButton(7, "▼", function() setTgpInputs(0, -1, 0) end, function() resetTgpInputs() end)
        setButton(10, "►", function() setTgpInputs(1, 0, 0) end, function() resetTgpInputs() end)
        setButton(11, "◄", function() setTgpInputs(-1, 0, 0) end, function() resetTgpInputs() end)
        
        setButton(14, "-", function() setTgpInputs(0, 0, -1) end, function() resetTgpInputs() end)
        setButton(15, "+", function() setTgpInputs(0, 0, 1) end, function() resetTgpInputs() end)
    elseif id == "page-wpn" then
        weaponListChanged = true;
    elseif id == "page-flt" then
        setButton(1, "MENU", function() mfd.SelectPage("page-menu") end)
        setButton(9, "FLAP", function() craft.Controls.Flaps = 0 end)
        setButton(10, "TRIM", function() craft.Controls.Trim = 0 end)
        setButton(11, "THR", function() craft.Controls.Throttle = 0 end)
        setButton(12, "VTOL", function() craft.Controls.Vtol = 0 end)
    end

    updateButtons()
end

-- Function to handle button press event from C#
function onMfdButtonPressed(id)
    if buttons[id] and buttons[id].onPress then
        buttons[id].onPress()
    end
end

-- Function to handle button release event from C#
function onMfdButtonReleased(id)
    if buttons[id] and buttons[id].onRelease then
        buttons[id].onRelease()
    end
end

function onWeaponListUpdated(o, a)
    weaponListChanged = true;
end

-- Function to initialize the MFD
function initialize()
    for id = 1, NumButtons do
        local widgetId = string.format("btn-%d", id)
        buttons[id] = {}
        buttons[id].buttonWidget = mfd.RootWidget:FindWidget(widgetId)
        if buttons[id].buttonWidget then
            buttons[id].buttonText = buttons[id].buttonWidget:FindWidget("btn-text")
        end
        resetButton(buttons[id])
    end

    tgpOnWidget = mfd.RootWidget:FindWidget("tgp-on");
    tgpDistanceWidget = mfd.RootWidget:FindWidget("tgp-distance");
    tgpOffWidget = mfd.RootWidget:FindWidget("tgp-off");

    targetNameWidget = mfd.RootWidget:FindWidget("target-name");

    craft.Targeting.WeaponListUpdated.add(onWeaponListUpdated);
end

-- Called every frame
function update()
    for i = 1, NumButtons do
        local button = buttons[i]
        if button and button.onUpdate then
            button.onUpdate()
        end
    end

    if pageId == "page-wpn" then
        if weaponListChanged  then
            weaponListChanged = false;
            buildWeaponsPage();
        end

        local target = craft.Targeting.Target;
        if target ~= nil then
            targetNameWidget:SetStyle("text", string.format("%s\n%s", target.Name, Utils.FormatNumber(target.Distance, UnitType.LongDistance, "0.0")));
        else
            targetNameWidget:SetStyle("text", "No Target");
        end

        buttons[7].buttonText:SetStyle("text", string.format("CMSR x%d", craft.Targeting.CountermeasureAmmo))
    elseif pageId == "page-tgp" then
        if craft.Targeting.TgpActive then
            tgpOnWidget.Visible = true;
            tgpOffWidget.Visible = false;
            tgpDistanceWidget.SetStyle("text", Utils.FormatNumber(craft.Targeting.TgpDistance, UnitType.LongDistance, "0.0"));
        else
            tgpOnWidget.Visible = false;
            tgpOffWidget.Visible = true;
        end
    end
end
