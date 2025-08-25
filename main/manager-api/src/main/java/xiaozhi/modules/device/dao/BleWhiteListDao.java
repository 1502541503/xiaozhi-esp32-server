package xiaozhi.modules.device.dao;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import xiaozhi.modules.device.entity.BleWhiteList;
import xiaozhi.modules.device.entity.DeviceEntity;

import java.util.Date;

@Mapper
public interface BleWhiteListDao extends BaseMapper<BleWhiteList> {
    /**
     * 根据蓝牙名称和固件标记检查设备是否在白名单中
     *
     * @param bleName 蓝牙名称
     * @param flag 固件标记
     * @return 如果设备在白名单中返回true，否则返回false
     */
    @Select("SELECT COUNT(*) > 0 FROM ble_white_list WHERE ble_name = #{bleName} AND flag = #{flag}")
    boolean isAuthorized(@Param("bleName") String bleName, @Param("flag") String flag);

}