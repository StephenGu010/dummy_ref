#ifndef REF_STM32F4_RGB_H
#define REF_STM32F4_RGB_H

#include <cstdint>
#include <tim.h>
#include <math.h>

#define MAX_LED 12
#define USE_BRIGHTNESS 0
#define PI               3.14159265358979f

class RGB
{
private:
    uint8_t LED_Data[MAX_LED][4];
    uint8_t LED_Mod[MAX_LED][4];  // for brightness
    uint32_t pwmData[(24*MAX_LED)+50];
    uint16_t  effStep = 0;
    uint8_t customColor[3] = {100, 100, 100};
public:
    uint8_t  data_sentflag = 0;

    enum Rgb_style_t
    {
        RAINBOW,
        // TIM
        FADE,
        BLINK,
        ALLRed,
        ALLGreen,
        ALLBlue,
        ALLOff,
        ALLWhite,
        CUSTOM_COLOR
    };


    RGB(uint8_t mode=0);

    void Run(Rgb_style_t _mode = RAINBOW);

    void Interrupt(uint8_t flag);
    void SetCustomColor(uint8_t _r, uint8_t _g, uint8_t _b)
    {
        customColor[0] = _r;
        customColor[1] = _g;
        customColor[2] = _b;
    }

    //functions
    void Set_LED (uint8_t LEDs, uint8_t Red, uint8_t Green, uint8_t Blue)
    {
        LED_Data[LEDs][0] = LEDs;
        LED_Data[LEDs][1] = Green;
        LED_Data[LEDs][2] = Red;
        LED_Data[LEDs][3] = Blue;
    }

    void Set_Brightness (int brightness)  // 0-45
    {
#if USE_BRIGHTNESS

        if (brightness > 45) brightness = 45;
        for (int i=0; i<MAX_LED; i++)
        {
            LED_Mod[i][0] = LED_Data[i][0];
            for (int j=1; j<4; j++)
            {
                float angle = 105-brightness;  // in degrees
                angle = angle*PI / 180;  // in rad
                LED_Mod[i][j] = (LED_Data[i][j])/(tan(angle));
            }
        }

#endif

    }

    void WS2812_Send (void)
    {
        uint32_t indx=0;
        uint32_t color;
        HAL_StatusTypeDef ret;

        for (int i= 0; i<MAX_LED; i++)
        {
#if USE_BRIGHTNESS
            color = ((LED_Mod[i][1]<<16) | (LED_Mod[i][2]<<8) | (LED_Mod[i][3]));
#else
            color = ((LED_Data[i][1]<<16) | (LED_Data[i][2]<<8) | (LED_Data[i][3]));
#endif
            for (int i=23; i>=0; i--)
            {
                //1 timing
                if (color&(1<<i))
                {
                    pwmData[indx] = 70;  // 2/3 of 105
                }
                //0 timing
                else pwmData[indx] = 30;  // 1/3 of 105
                indx++;
            }

        }

        //for reset between two data cycle
        for (int i=0; i<30; i++)
        {
            pwmData[indx] = 0;
            indx++;
        }

        ret = HAL_TIM_PWM_Start_DMA(&htim2, TIM_CHANNEL_4, pwmData, indx);
        if (ret != HAL_OK) {
            data_sentflag = 0;
            return;
        }
        while (!data_sentflag){};
        data_sentflag = 0;
    }

    void RainBow()
    {
        float factor1, factor2;
        uint16_t ind;
        for(uint16_t j=0;j<MAX_LED;j++) {
            ind = effStep + j * 1;
            switch((int)((ind % 12) / 4)) {
                case 0: factor1 = 1.0 - ((float)(ind % 12 - 0 * 4) / 4);
                    factor2 = (float)((int)(ind - 0) % 12) / 4;
                    Set_LED(j, 255 * factor1 + 0 * factor2, 0 * factor1 + 255 * factor2, 0 * factor1 + 0 * factor2);
                    WS2812_Send();
                    break;
                case 1: factor1 = 1.0 - ((float)(ind % 12 - 1 * 4) / 4);
                    factor2 = (float)((int)(ind - 4) % 12) / 4;
                    Set_LED(j, 0 * factor1 + 0 * factor2, 255 * factor1 + 0 * factor2, 0 * factor1 + 255 * factor2);
                    WS2812_Send();
                    break;
                case 2: factor1 = 1.0 - ((float)(ind % 12 - 2 * 4) / 4);
                    factor2 = (float)((int)(ind - 8) % 12) / 4;
                    Set_LED(j, 0 * factor1 + 255 * factor2, 0 * factor1 + 0 * factor2, 255 * factor1 + 0 * factor2);
                    WS2812_Send();
                    break;
            }
        }
        if(effStep >= 12) {effStep = 0; }
        else effStep++;
    }

    void Sequence() {
        //define your color style here
    }

    void Blink()
    {
        uint8_t e,r,g,b;
        if(effStep < 44) {
            for(uint16_t j=0;j<MAX_LED;j++)
            {
                Set_LED(j, 0, 0, 0);
                WS2812_Send();
            }
        }
        else if(effStep  < 46) {
            e = (effStep * 5) - 220;
            r = 255 * ( e / 10 ) + 0 * ( 1.0 - e / 10 );
            g = 255 * ( e / 10 ) + 0 * ( 1.0 - e / 10 );
            b = 255 * ( e / 10 ) + 0 * ( 1.0 - e / 10 );
            for(uint16_t j=0;j<12;j++)
                if((j%1)==0)
                {
                    Set_LED(j, r, g, b);
                    WS2812_Send();
                }
                else
                {
                    Set_LED(j, 0, 0, 0);
                    WS2812_Send();
                }
        }
        else if(effStep < 53.6) {
            for(uint16_t j=0;j<MAX_LED;j++)
                if((j%1)==0)
                {
                    Set_LED(j, 255, 255, 255);
                    WS2812_Send();
                }
                else
                {
                    Set_LED(j, 0, 0, 0);
                    WS2812_Send();
                }
        }
        else if(effStep < 55.6) {
            e = (effStep * 5) - 268;
            r = 0 * ( e / 10 ) + 255 * ( 1.0 - e / 10 );
            g = 0 * ( e / 10 ) + 255 * ( 1.0 - e / 10 );
            b = 0 * ( e / 10 ) + 255 * ( 1.0 - e / 10 );
            for(uint16_t j=0;j<MAX_LED;j++)
                if((j%1)==0)
                {
                    Set_LED(j, r, g, b);
                    WS2812_Send();
                }
                else
                {
                    Set_LED(j, 0, 0, 0);
                    WS2812_Send();
                }
        }
        else {
            for(uint16_t j=0;j<MAX_LED;j++)
            {
                Set_LED(j, 0, 0, 0);
                WS2812_Send();
            }
        }
        if(effStep >= 75.6) {effStep = 0; }
        else effStep++;
    }

    void Fade() {
        uint8_t r,g,b;
        double e;
        e = (effStep * 20) / (double)703;
        r = ( e ) * 255 + 0 * ( 1.0 - e );
        g = ( e ) * 255 + 0 * ( 1.0 - e );
        b = ( e ) * 255 + 0 * ( 1.0 - e );
        for(uint16_t j=0;j<MAX_LED;j++) {
            if((j % 1) == 0)
            {
                Set_LED(j, r, g, b);
                WS2812_Send();
            }
            else
            {
                Set_LED(j, 0, 0, 0);
                WS2812_Send();
            }
        }
        if(effStep >= 35.15) {effStep = 0; }
        else effStep++;
    }

    void PureColor(Rgb_style_t color) {
        uint8_t r,g,b;
        switch (color){
            case ALLRed:
                r = 100;
                g = 0;
                b = 0;
                break;
            case ALLBlue:
                r = 0;
                g = 0;
                b = 100;
                break;
            case ALLGreen:
                r = 0;
                g = 100;
                b = 0;
                break;
            case ALLOff:
                r = 0;
                g = 0;
                b = 0;
                break;
            case ALLWhite:
                r = 100;
                g = 100;
                b = 120;
                break;
            default:
                break;
        }
        for(uint16_t j=0;j<MAX_LED;j++) {
            Set_LED(j, r, g, b);
            WS2812_Send();
        }
    }

    void CustomColor() {
        for(uint16_t j=0;j<MAX_LED;j++) {
            Set_LED(j, customColor[0], customColor[1], customColor[2]);
            WS2812_Send();
        }
    }

};

#endif //REF_STM32F4_RGB_H
