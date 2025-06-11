package xiaozhi.modules.api;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import xiaozhi.modules.device.entity.DeviceMacEntity;
import xiaozhi.modules.device.entity.ResponseWrapper;

@FeignClient(name = "iotSolutionClient", url = "${iot.solution.url}")
public interface IotSolutionClient {

    /**
     * 查询mac是否授权
     * @param mac:
     * @param platform:
     * @author zzq
     */
    @GetMapping(value = "/authApi/hasAIAuth")
    ResponseWrapper<Boolean> getMac(@RequestParam("mac") String mac,@RequestParam("platform") Integer platform);
}