#include "rgb.hpp"

RGB::RGB(uint8_t m) {
    //init here
}

void RGB::Run(RGB::Rgb_style_t mode) {
    switch (mode) {
        case RAINBOW: {
            RainBow();
            break;
        }
        case FADE:{
            Fade();
            break;
        }
        case BLINK:{
            Blink();
            break;
        }
        case ALLRed:{
            PureColor(ALLRed);
            break;
        }
        case ALLGreen:{
            PureColor(ALLGreen);
            break;
        }
        case ALLBlue:{
            PureColor(ALLBlue);
            break;
        }
        case ALLOff:{
            PureColor(ALLOff);
            break;
        }
        case ALLWhite:{
            PureColor(ALLWhite);
            break;
        }
        case CUSTOM_COLOR:{
            CustomColor();
            break;
        }
        default:
            break;
    }
}

void RGB::Interrupt(uint8_t flag) {
    data_sentflag = flag;
}
