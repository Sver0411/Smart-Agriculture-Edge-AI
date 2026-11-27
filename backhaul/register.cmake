# The scheduler project configures XQUIC before this deferred target is created.
cmake_language(DEFER CALL include "${AGRI_BRIDGE_SOURCE}/target.cmake")
