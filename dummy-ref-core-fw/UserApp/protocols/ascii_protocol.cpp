#include "common_inc.h"

extern DummyRobot dummy;

static void HandleBangCommand(const char* _cmd, StreamSink &_responseChannel)
{
    std::string s(_cmd);
    if (s.find("STOP") != std::string::npos)
    {
        dummy.commandHandler.EmergencyStop();
        Respond(_responseChannel, "Stopped ok");
    } else if (s.find("START") != std::string::npos)
    {
        dummy.SetEnable(true);
        Respond(_responseChannel, "Started ok");
    } else if (s.find("HOME") != std::string::npos)
    {
        dummy.Homing();
        Respond(_responseChannel, "Homing ok");
    } else if (s.find("CALIBRATION") != std::string::npos)
    {
        dummy.CalibrateHomeOffset();
        Respond(_responseChannel, "calibration ok");
    } else if (s.find("RESET") != std::string::npos)
    {
        dummy.Resting();
        Respond(_responseChannel, "Started ok");
    } else if (s.find("DISABLE") != std::string::npos)
    {
        dummy.SetEnable(false);
        Respond(_responseChannel, "Disabled ok");
    } else if (s.find("LEDON") != std::string::npos)
    {
        dummy.SetLedEnable(true);
        Respond(_responseChannel, "ok LED ON");
    } else if (s.find("LEDOFF") != std::string::npos)
    {
        dummy.SetLedEnable(false);
        Respond(_responseChannel, "ok LED OFF");
    } else if (s.find("RGBON") != std::string::npos)
    {
        dummy.SetRGBEnable(true);
        Respond(_responseChannel, "ok RGB ON");
    } else if (s.find("RGBOFF") != std::string::npos)
    {
        dummy.SetRGBEnable(false);
        Respond(_responseChannel, "ok RGB OFF");
    }
}

static void HandleHashCommand(const char* _cmd, StreamSink &_responseChannel)
{
    std::string s(_cmd);
    if (s.find("GETJPOS") != std::string::npos)
    {
        Respond(_responseChannel, "ok %.2f %.2f %.2f %.2f %.2f %.2f",
                dummy.currentJoints.a[0], dummy.currentJoints.a[1],
                dummy.currentJoints.a[2], dummy.currentJoints.a[3],
                dummy.currentJoints.a[4], dummy.currentJoints.a[5]);
    } else if (s.find("GETLPOS") != std::string::npos)
    {
        dummy.UpdateJointPose6D();
        Respond(_responseChannel, "ok %.2f %.2f %.2f %.2f %.2f %.2f",
                dummy.currentPose6D.X, dummy.currentPose6D.Y,
                dummy.currentPose6D.Z, dummy.currentPose6D.A,
                dummy.currentPose6D.B, dummy.currentPose6D.C);
    } else if (s.find("SET_DCE_KP") != std::string::npos)
    {
        uint32_t kp;
        uint32_t node;
        sscanf(_cmd, "#SET_DCE_KP %lu %lu", &node, &kp);
        if (node >= 1 && node <= 6)
        {
            dummy.motorJ[node]->SetDceKp(kp);
            Respond(_responseChannel, "ok SET MOTOR [%lu] DCE_KP [%lu]", node, kp);
        } else
        {
            Respond(_responseChannel, "error SET MOTOR [%lu] DCE_KP [%lu] is wrong", node, kp);
        }
    } else if (s.find("SET_DCE_KI") != std::string::npos)
    {
        uint32_t ki;
        uint32_t node;
        sscanf(_cmd, "#SET_DCE_KI %lu %lu", &node, &ki);
        if (node >= 1 && node <= 6)
        {
            dummy.motorJ[node]->SetDceKi(ki);
            Respond(_responseChannel, "ok SET MOTOR [%lu] DCE_KI [%lu]", node, ki);
        } else
        {
            Respond(_responseChannel, "error SET MOTOR [%lu] DCE_KI [%lu] is wrong", node, ki);
        }
    } else if (s.find("SET_DCE_KD") != std::string::npos)
    {
        uint32_t kd;
        uint32_t node;
        sscanf(_cmd, "#SET_DCE_KD %lu %lu", &node, &kd);
        if (node >= 1 && node <= 6)
        {
            dummy.motorJ[node]->SetDceKd(kd);
            Respond(_responseChannel, "ok SET MOTOR [%lu] DCE_KD [%lu]", node, kd);
        } else
        {
            Respond(_responseChannel, "error SET MOTOR [%lu] DCE_KD [%lu] is wrong", node, kd);
        }
    } else if (s.find("REBOOT") != std::string::npos)
    {
        uint32_t node;
        sscanf(_cmd, "#REBOOT %lu", &node);
        if (node >= 1 && node <= 6)
        {
            dummy.motorJ[node]->Reboot();
            Respond(_responseChannel, "ok REBOOT MOTOR [%lu]", node);
        } else
        {
            Respond(_responseChannel, "error REBOOT MOTOR [%lu] is wrong", node);
        }
    } else if (s.find("CMDMODE") != std::string::npos)
    {
        uint32_t mode;
        if (sscanf(_cmd, "#CMDMODE %lu", &mode) == 1)
        {
            dummy.SetCommandMode(mode);
            Respond(_responseChannel, "ok Set command mode to [%lu] (%s)", mode,
                    DummyRobot::GetCommandModeShortName(dummy.GetCommandMode()));
        } else
        {
            Respond(_responseChannel, "error BAD_CMDMODE");
        }
    } else if (s.find("GETMODE") != std::string::npos)
    {
        uint32_t mode = dummy.GetCommandMode();
        Respond(_responseChannel, "ok %lu %s", mode, DummyRobot::GetCommandModeShortName(mode));
    } else if (s.find("GETENABLE") != std::string::npos)
    {
        Respond(_responseChannel, "ok %d", dummy.IsEnabled() ? 1 : 0);
    } else if (s.find("RGBMODE") != std::string::npos)
    {
        uint32_t mode;
        if (sscanf(_cmd, "#RGBMODE %lu", &mode) == 1)
        {
            dummy.SetRGBMode(mode);
            Respond(_responseChannel, "ok RGBMODE [%lu]", dummy.GetRGBMode());
        } else
        {
            Respond(_responseChannel, "error BAD_RGBMODE");
        }
    } else if (s.find("RGBCOLOR") != std::string::npos)
    {
        uint32_t r;
        uint32_t g;
        uint32_t b;
        if (sscanf(_cmd, "#RGBCOLOR %lu %lu %lu", &r, &g, &b) == 3)
        {
            if (r > 255 || g > 255 || b > 255)
            {
                Respond(_responseChannel, "error RGB_OUT_OF_RANGE");
            } else
            {
                dummy.SetRGBColor((uint8_t) r, (uint8_t) g, (uint8_t) b);
                dummy.SetRGBMode(RGB::CUSTOM_COLOR);
                Respond(_responseChannel, "ok RGBCOLOR [%lu %lu %lu]", r, g, b);
            }
        } else
        {
            Respond(_responseChannel, "error BAD_RGBCOLOR");
        }
    } else if (s.find("GETRGB") != std::string::npos)
    {
        uint8_t r = 0;
        uint8_t g = 0;
        uint8_t b = 0;
        dummy.GetRGBColor(r, g, b);
        Respond(_responseChannel, "ok %d %lu %u %u %u %d",
                dummy.GetRGBEnabled() ? 1 : 0,
                dummy.GetRGBMode(),
                (unsigned int) r,
                (unsigned int) g,
                (unsigned int) b,
                dummy.GetLedEnabled() ? 1 : 0);
    } else
    {
        Respond(_responseChannel, "ok");
    }
}

void OnUsbAsciiCmd(const char* _cmd, size_t _len, StreamSink &_responseChannel)
{
    /*---------------------------- ↓ Add Your CMDs Here ↓ -----------------------------*/
    if (_cmd[0] == '!')
    {
        HandleBangCommand(_cmd, _responseChannel);
    } else if (_cmd[0] == '#')
    {
        HandleHashCommand(_cmd, _responseChannel);
    } else if (_cmd[0] == '>' || _cmd[0] == '@' || _cmd[0] == '&')
    {
        uint32_t freeSize = dummy.commandHandler.Push(_cmd);
        Respond(_responseChannel, "%d", freeSize);
    } else if (_cmd[0] == '$')
    {
        // '$' command: per-joint current setpoints in Ampere.
        uint32_t freeSize = dummy.commandHandler.Push(_cmd);
        if (freeSize == 0xFF)
            Respond(_responseChannel, "error CMD FIFO FULL");
    }

/*---------------------------- ↑ Add Your CMDs Here ↑ -----------------------------*/
}


void OnUart4AsciiCmd(const char* _cmd, size_t _len, StreamSink &_responseChannel)
{
    /*---------------------------- ↓ Add Your CMDs Here ↓ -----------------------------*/
    if (_cmd[0] == '!')
    {
        HandleBangCommand(_cmd, _responseChannel);
    } else if (_cmd[0] == '#')
    {
        HandleHashCommand(_cmd, _responseChannel);
    } else if (_cmd[0] == '>' || _cmd[0] == '@' || _cmd[0] == '&')
    {
        uint32_t freeSize = dummy.commandHandler.Push(_cmd);
        Respond(_responseChannel, "%d", freeSize);
    } else if (_cmd[0] == '$')
    {
        // '$' command: per-joint current setpoints in Ampere.
        uint32_t freeSize = dummy.commandHandler.Push(_cmd);
        if (freeSize == 0xFF)
            Respond(_responseChannel, "error CMD FIFO FULL");
    }
/*---------------------------- ↑ Add Your CMDs Here ↑ -----------------------------*/
}


void OnUart5AsciiCmd(const char* _cmd, size_t _len, StreamSink &_responseChannel)
{
    /*---------------------------- ↓ Add Your CMDs Here ↓ -----------------------------*/

/*---------------------------- ↑ Add Your CMDs Here ↑ -----------------------------*/
}
