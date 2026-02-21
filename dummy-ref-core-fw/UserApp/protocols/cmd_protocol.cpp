
#include "common_inc.h"

/*----------------- 1.Add Your Extern Variables Here (Optional) ------------------*/
extern DummyRobot dummy;
#define TEST_ADC_CHANNEL_0 0
class HelperFunctions
{
public:
    /*--------------- 2.Add Your Helper Functions Helper Here (optional) ----------------*/
    float GetTemperatureHelper()
    {
        return AdcGetChipTemperature();
    }

    /*just AN test for how to add a new CLI command through fibre protocol*/
    float GetVoltageHelper()
    {
        return AdcGetVoltage(TEST_ADC_CHANNEL_0);
    }


} staticFunctions;


// Define options that intractable with "reftool".
static inline auto MakeObjTree()
{
    /*--------------- 3.Add Your Protocol Variables & Functions Here ----------------*/
    return make_protocol_member_list(
        // Add Read-Only Variables
        make_protocol_ro_property("serial_number", &serialNumber),
        make_protocol_function("get_temperature", staticFunctions, &HelperFunctions::GetTemperatureHelper),
        make_protocol_function("get_voltage", staticFunctions, &HelperFunctions::GetVoltageHelper),
        make_protocol_object("robot", dummy.MakeProtocolDefinitions())
    );
}


COMMIT_PROTOCOL
