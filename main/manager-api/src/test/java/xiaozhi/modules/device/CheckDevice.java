package xiaozhi.modules.device;

import cn.hutool.json.JSON;
import cn.hutool.json.JSONObject;
import lombok.extern.slf4j.Slf4j;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import xiaozhi.AdminApplication;
import xiaozhi.modules.api.IotSolutionClient;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.sys.dto.SysUserDTO;

import java.util.UUID;

@SpringBootTest(classes = AdminApplication.class)
@DisplayName("设备测试")
public class CheckDevice {


}
