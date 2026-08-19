#!/usr/bin/env python3
"""Build preparation and verification interface for RM2100 firmware."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_ENABLED_OPTIONS = frozenset(
    {
        "CONFIG_FIRMWARE_CPU_800MHZ",
        "CONFIG_FIRMWARE_CPU_900MHZ",
        "CONFIG_FIRMWARE_CPU_1000MHZ",
        "CONFIG_FIRMWARE_ENABLE_IPV6",
        "CONFIG_FIRMWARE_INCLUDE_HTTPS",
        "CONFIG_FIRMWARE_INCLUDE_IPSET",
        "CONFIG_FIRMWARE_INCLUDE_LANG_CN",
        "CONFIG_FIRMWARE_INCLUDE_OPENSSL_EC",
        "CONFIG_FIRMWARE_INCLUDE_OPENSSL_EXE",
        "CONFIG_FIRMWARE_INCLUDE_SFE",
    }
)
REQUIRED_PROFILE_VALUES = {
    "CONFIG_FIRMWARE_INCLUDE_SFE": "y",
    "CONFIG_VENDOR": "Ralink",
    "CONFIG_PRODUCT": "MT7621",
    "CONFIG_FIRMWARE_PRODUCT_ID": '"RM2100"',
    "CONFIG_LINUXDIR": "linux-3.4.x",
    "CONFIG_FIRMWARE_KERNEL_CONFIG": '"kernel-3.4.x-5.0.config"',
    "CONFIG_FIRMWARE_WIFI2_DRIVER": "4.1",
    "CONFIG_FIRMWARE_WIFI5_DRIVER": "5.0.5.1",
    "CONFIG_FIRMWARE_WLAN_COUNTRY_CODE": '"AU"',
    "CONFIG_FIRMWARE_ENABLE_IPV6": "y",
    "CONFIG_FIRMWARE_INCLUDE_IPSET": "y",
    "CONFIG_FIRMWARE_INCLUDE_LANG_CN": "y",
    "CONFIG_FIRMWARE_INCLUDE_HTTPS": "y",
    "CONFIG_FIRMWARE_INCLUDE_OPENSSL_EC": "y",
    "CONFIG_FIRMWARE_INCLUDE_OPENSSL_EXE": "y",
}
CPU_PROFILE_OPTIONS = {
    "800": "CONFIG_FIRMWARE_CPU_800MHZ",
    "900": "CONFIG_FIRMWARE_CPU_900MHZ",
    "1000": "CONFIG_FIRMWARE_CPU_1000MHZ",
}
KERNEL_CPU_OPTIONS = {
    "800": "CONFIG_RALINK_MT7621_PLL800",
    "900": "CONFIG_RALINK_MT7621_PLL900",
    "1000": "CONFIG_RALINK_MT7621_PLL1000",
}
CPU_FREQUENCIES = ("bootloader", *CPU_PROFILE_OPTIONS)
KERNEL_BASELINE = {
    "CONFIG_RALINK_MT7621": "y",
    "CONFIG_SMP": "y",
    "CONFIG_NR_CPUS": "4",
    "CONFIG_HZ": "250",
    "CONFIG_PREEMPT_NONE": "y",
    "CONFIG_SHORTCUT_FE": "y",
    "CONFIG_NF_CONNTRACK_EVENTS": "y",
    "CONFIG_RPS": "y",
    "CONFIG_XPS": "y",
}
IMAGE_HEADER = struct.Struct(">7I4B28sI")
IMAGE_MAGIC = 0x27051956
MIN_IMAGE_SIZE = 4 * 1024 * 1024
MAX_IMAGE_SIZE = 16 * 1024 * 1024
BUNDLE_METADATA_FILES = (
    "manifest.json",
    "build-lock.json",
    "rm2100-3.4.config",
    "kernel-3.4.config",
    "performance-profile.json",
    "runtime-policy.json",
    "build-warning-policy.json",
)
BUNDLE_CHECKSUM_FILE = "SHA256SUMS"
REPRODUCIBILITY_REPORT_FILE = "reproducibility-policy.json"
SFE_DEFAULT_DISABLED = '\t{ "sfe_enable", "0" },'
SFE_DEFAULT_ENABLED = '\t{ "sfe_enable", "1" },'
SFE_RUNTIME_ORIGINAL = """\
\tif (sfe_loaded && !sfe_enable) {
\t\tmodule_smart_unload("fast_classifier", 1);
\t\tdoSystem("echo 1 > /proc/sys/net/netfilter/nf_conntrack_tcp_be_liberal");
\t\tdoSystem("echo 1 > /proc/sys/net/netfilter/nf_conntrack_tcp_no_window_check");
\t\tsfe_loaded = 0;
\t}
\tif (sfe_enable && !sfe_loaded) {
\t\tdoSystem("echo 0 > /proc/sys/net/netfilter/nf_conntrack_tcp_be_liberal");
\t\tdoSystem("echo 0 > /proc/sys/net/netfilter/nf_conntrack_tcp_no_window_check");
\t\tmodule_smart_load("fast_classifier", NULL);
\t\tsfe_loaded = 1;
\t}
\tif (sfe_loaded) {
\t\tif (sfe_enable == 1)
\t\t\tdoSystem("echo 0 > /sys/fast_classifier/skip_to_bridge_ingress");
\t\telse if (sfe_enable == 2)
\t\t\tdoSystem("echo 1 > /sys/fast_classifier/skip_to_bridge_ingress");
\t}
"""
SFE_RUNTIME_HARDENED = """\
\tif (sfe_loaded && !sfe_enable) {
\t\tmodule_smart_unload("fast_classifier", 1);
\t\tsfe_loaded = is_module_loaded("fast_classifier");
\t\tif (!sfe_loaded) {
\t\t\tdoSystem("echo 1 > /proc/sys/net/netfilter/nf_conntrack_tcp_be_liberal");
\t\t\tdoSystem("echo 1 > /proc/sys/net/netfilter/nf_conntrack_tcp_no_window_check");
\t\t} else {
\t\t\tlogmessage(LOGNAME, "%s", "SFE module unload failed");
\t\t}
\t}
\tif (sfe_enable && !sfe_loaded) {
\t\tdoSystem("echo 0 > /proc/sys/net/netfilter/nf_conntrack_tcp_be_liberal");
\t\tdoSystem("echo 0 > /proc/sys/net/netfilter/nf_conntrack_tcp_no_window_check");
\t\tmodule_smart_load("fast_classifier", NULL);
\t\tsfe_loaded = is_module_loaded("fast_classifier");
\t\tif (!sfe_loaded) {
\t\t\tdoSystem("echo 1 > /proc/sys/net/netfilter/nf_conntrack_tcp_be_liberal");
\t\t\tdoSystem("echo 1 > /proc/sys/net/netfilter/nf_conntrack_tcp_no_window_check");
\t\t\tlogmessage(LOGNAME, "%s", "SFE module load failed");
\t\t}
\t}
\tif (sfe_loaded) {
\t\tif (sfe_enable == 1)
\t\t\tdoSystem("echo 0 > /sys/fast_classifier/skip_to_bridge_ingress");
\t\telse if (sfe_enable == 2)
\t\t\tdoSystem("echo 1 > /sys/fast_classifier/skip_to_bridge_ingress");
\t}
"""
USERLAND_SOURCE_PATCHES = (
    (
        "trunk/user/rc/rc.c",
        '#include "rc.h"\n#include "gpio_pins.h"',
        '#include "rc.h"\n#include <flash_mtd.h>\n#include "gpio_pins.h"',
        "rc flash MTD prototype",
    ),
    (
        "trunk/user/802.1x/rtdot1x.c",
        "#include <stdlib.h>\n#include <stdio.h>",
        "#include <ctype.h>\n#include <stdlib.h>\n#include <stdio.h>",
        "802.1X ctype prototype",
    ),
    (
        "trunk/user/802.1x/rtdot1x.c",
        "\t\tif (isdigit(prefix_name[c-1]))",
        "\t\tif (isdigit((unsigned char)prefix_name[c-1]))",
        "802.1X ctype argument",
    ),
    (
        "trunk/user/accel-pptpd/pptpd-1.3.3/compat.c",
        '#include "compat.h"\n\n#ifndef HAVE_STRLCPY\n#include <string.h>\n#include <stdio.h>',
        '#include "compat.h"\n\n#include <string.h>\n\n#ifndef HAVE_STRLCPY\n#include <stdio.h>',
        "PPTP memset prototype",
    ),
    (
        "trunk/user/accel-pptpd/pptpd-1.3.3/bcrelay.c",
        '  if (ifin == "") {\n'
        '       syslog(LOG_INFO,"Incoming interface required!");\n'
        "       showusage(argv[0]);\n"
        "       _exit(1);\n"
        "  }\n"
        '  if (ifout == "" && ipsec == "") {\n',
        "  if (*ifin == '\\0') {\n"
        '       syslog(LOG_INFO,"Incoming interface required!");\n'
        "       showusage(argv[0]);\n"
        "       _exit(1);\n"
        "  }\n"
        "  if (*ifout == '\\0' && *ipsec == '\\0') {\n",
        "PPTP interface argument checks",
    ),
    (
        "trunk/user/accel-pptpd/pptpd-1.3.3/bcrelay.c",
        "  } else {\n"
        '        sprintf(interfaces,"%s|%s", ifin, ifout);\n'
        "  }",
        "  } else {\n"
        '        c = snprintf(interfaces, sizeof(interfaces), "%s|%s", ifin, ifout);\n'
        "        if (c < 0 || c >= (int)sizeof(interfaces)) {\n"
        '                syslog(LOG_ERR, "Interface filter is too long");\n'
        "                _exit(1);\n"
        "        }\n"
        "  }",
        "PPTP bounded interface filter",
    ),
    (
        "trunk/user/accel-pptpd/pptpd-1.3.3/bcrelay.c",
        '    } else if (ipsec != "" && strncmp(ifs.ifc_req[i].ifr_name, "ipsec", 5) == 0) {',
        "    } else if (*ipsec != '\\0' && "
        'strncmp(ifs.ifc_req[i].ifr_name, "ipsec", 5) == 0) {',
        "PPTP IPsec argument check",
    ),
    (
        "trunk/user/lanauth/lanauth.c",
        "\tif (!pass || !*pass) usage();",
        "\tif (!*pass) usage();",
        "LAN auth password check",
    ),
    (
        "trunk/user/udpxy/util.c",
        'static char s_sysinfo [80] = "\\0";',
        'static char s_sysinfo [200] = "\\0";',
        "udpxy system information buffer",
    ),
    (
        "trunk/user/udpxy/util.c",
        "        (void) snprintf (s_sysinfo, sizeof(s_sysinfo)-1, \"%s %s %s\",",
        "        (void) snprintf (s_sysinfo, sizeof(s_sysinfo), \"%s %s %s\",",
        "udpxy bounded system information write",
    ),
    (
        "trunk/user/wireless_tools/ifrename.c",
        "\t  usage(); \n\tcase 'c':",
        "\t  usage(); \n\t  break;\n\tcase 'c':",
        "ifrename usage fallthrough",
    ),
    (
        "trunk/user/miniupnpd/miniupnpd-2.x/upnpevents.c",
        "\t\t\t\tif(obj->state != EConnecting)\n"
        "\t\t\t\t\tbreak;\n"
        "\t\t\tcase EConnecting:",
        "\t\t\t\tif(obj->state != EConnecting)\n"
        "\t\t\t\t\tbreak;\n"
        "\t\t\t\t/* fall through */\n"
        "\t\t\tcase EConnecting:",
        "miniupnpd connection-state fallthrough",
    ),
    (
        "trunk/user/xl2tpd/xl2tpd.c",
        "#ifdef USE_KERNEL\n"
        "                 if (!kernel_support)\n"
        "#endif\n"
        "                    close (c->fd);\n"
        "                    c->fd = -1;",
        "#ifdef USE_KERNEL\n"
        "                 if (!kernel_support) {\n"
        "#endif\n"
        "                    close (c->fd);\n"
        "#ifdef USE_KERNEL\n"
        "                 }\n"
        "#endif\n"
        "                    c->fd = -1;",
        "xl2tpd conditional close scope",
    ),
    (
        "trunk/user/accel-pptpd/pptpd-1.3.3/bcrelay.c",
        "/* uncomment if you compile this without poptop's configure script */\n"
        "#define HAVE_FORK",
        "/* uncomment if you compile this without poptop's configure script */\n"
        "#ifndef HAVE_FORK\n#define HAVE_FORK\n#endif",
        "PPTP configure feature guard",
    ),
    (
        "trunk/user/httpd/aspbw.c",
        "\tif (( len >= 2) &&\n"
        "\t\t(the_char >= '0' && the_char <= '9')\n"
        "\t\t|| (the_char >= 'A' && the_char <= 'Z')\n"
        "\t\t|| (the_char >= 'a' && the_char <= 'z')\n"
        "\t\t|| the_char == '!' || the_char == '*'\n"
        "\t\t|| the_char == '(' || the_char == ')'\n"
        "\t\t|| the_char == '_' || the_char == '-'\n"
        "\t\t|| the_char == '\\'' || the_char == '.') ",
        "\tif ((len >= 2) && (\n"
        "\t\t(the_char >= '0' && the_char <= '9')\n"
        "\t\t|| (the_char >= 'A' && the_char <= 'Z')\n"
        "\t\t|| (the_char >= 'a' && the_char <= 'z')\n"
        "\t\t|| the_char == '!' || the_char == '*'\n"
        "\t\t|| the_char == '(' || the_char == ')'\n"
        "\t\t|| the_char == '_' || the_char == '-'\n"
        "\t\t|| the_char == '\\'' || the_char == '.'))",
        "HTTP ASCII hex length scope",
    ),
    (
        "trunk/user/httpd/https.c",
        "static void\n"
        "http_ssl_info_cb(const SSL *ssl, int where, int ret)\n"
        "{\n"
        "\t/* disable SSL renegotiation */\n"
        "\tif (where & SSL_CB_HANDSHAKE_DONE) {\n"
        "#if OPENSSL_VERSION_NUMBER < 0x10100000L\n"
        "\t\tssl->s3->flags |= SSL3_FLAGS_NO_RENEGOTIATE_CIPHERS;\n"
        "#else\n"
        "\t\tSSL_set_options(ssl, SSL_OP_NO_RENEGOTIATION);\n"
        "#endif\n"
        "\t}\n"
        "}",
        "#if OPENSSL_VERSION_NUMBER < 0x10101000L\n"
        "static void\n"
        "http_ssl_info_cb(const SSL *ssl, int where, int ret)\n"
        "{\n"
        "\t/* disable SSL renegotiation */\n"
        "\tif (where & SSL_CB_HANDSHAKE_DONE) {\n"
        "#if OPENSSL_VERSION_NUMBER < 0x10100000L\n"
        "\t\tssl->s3->flags |= SSL3_FLAGS_NO_RENEGOTIATE_CIPHERS;\n"
        "#else\n"
        "\t\tSSL_set_options((SSL *)ssl, SSL_OP_NO_RENEGOTIATION);\n"
        "#endif\n"
        "\t}\n"
        "}\n"
        "#endif",
        "HTTPS legacy renegotiation callback scope",
    ),
    (
        "trunk/user/httpd/https.c",
        "\tssl_options = SSL_OP_ALL | SSL_OP_NO_COMPRESSION | SSL_OP_NO_SSLv2 | "
        "SSL_OP_NO_SSLv3 |\n"
        "\t\t\tSSL_OP_NO_SESSION_RESUMPTION_ON_RENEGOTIATION;\n\n"
        "\tSSL_CTX_set_options(ssl_ctx, ssl_options);",
        "\tssl_options = SSL_OP_ALL | SSL_OP_NO_COMPRESSION | SSL_OP_NO_SSLv2 | "
        "SSL_OP_NO_SSLv3 |\n"
        "\t\t\tSSL_OP_NO_SESSION_RESUMPTION_ON_RENEGOTIATION;\n"
        "#if OPENSSL_VERSION_NUMBER >= 0x10101000L\n"
        "\tssl_options |= SSL_OP_NO_RENEGOTIATION;\n"
        "#endif\n\n"
        "\tSSL_CTX_set_options(ssl_ctx, ssl_options);",
        "HTTPS context renegotiation policy",
    ),
    (
        "trunk/user/httpd/https.c",
        "\tSSL_CTX_set_info_callback(ssl_ctx, http_ssl_info_cb);",
        "#if OPENSSL_VERSION_NUMBER < 0x10101000L\n"
        "\tSSL_CTX_set_info_callback(ssl_ctx, http_ssl_info_cb);\n"
        "#endif",
        "HTTPS legacy callback registration",
    ),
    (
        "trunk/user/ebtables/ebtables-2.0.10-4/communication.c",
        "close_file:\n\tfclose(file);\n\treturn 0;",
        "close_file:\n"
        "\tif (fclose(file) != 0 && ret == 0) {\n"
        "\t\tebt_print_error(\"Could not close file %s\", filename);\n"
        "\t\tret = -1;\n"
        "\t}\n"
        "\treturn ret;",
        "ebtables counter file result",
    ),
    (
        "trunk/user/ebtables/ebtables-2.0.10-4/ebtables.c",
        "\t\tif (replace->nentries)\n\t\t\tebt_deliver_counters(replace);\n\t}\n"
        "\treturn 0;",
        "\t\tif (replace->nentries) {\n"
        "\t\t\tebt_deliver_counters(replace);\n"
        "\t\t\tif (ebt_errormsg[0] != '\\0')\n"
        "\t\t\t\treturn -1;\n"
        "\t\t}\n\t}\n"
        "\treturn 0;",
        "ebtables counter error propagation",
    ),
)
WIRELESS_SOURCE_PATCHES = (
    (
        "trunk/proprietary/rt_wifi/rtpci/5.0.5.1/mt7615/txpwr/single_sku.c",
        "\tif ((ucPhymode == MODE_HTMIX) || (ucPhymode == MODE_HTGREENFIELD)) {\n"
        "\t\tucNss = (ucMCS >> 3) + 1;\n"
        "\t\tucMCS &= 0x7;\n"
        "\t}",
        "\tif ((ucPhymode == MODE_HTMIX) || (ucPhymode == MODE_HTGREENFIELD)) {\n"
        "\t\tucNss = (ucMCS >> 3) + 1;\n"
        "\t\tucMCS &= 0x7;\n"
        "\t}\n\n"
        "\tif ((ucNss == 0) || (ucNss > SKU_TX_SPATIAL_STREAM_NUM))\n"
        "\t\tucNss = 1;\n"
        "\tucNSS = ucNss - 1;",
        "MT7615 spatial-stream index validation",
    ),
    (
        "trunk/proprietary/rt_wifi/rtpci/5.0.5.1/mt7615/txpwr/single_sku.c",
        "cTxPowerCompBackup[ucBandIdx][ucRateOffset][ucNSS - 1]",
        "cTxPowerCompBackup[ucBandIdx][ucRateOffset][ucNSS]",
        "MT7615 zero-based spatial-stream lookup",
    ),
)
HOST_BUILD_SOURCE_PATCHES = (
    (
        "trunk/user/busybox/busybox-1.24.x/scripts/basic/split-include.c",
        "\t    fgets(old_line, buffer_size, fp_target);",
        "\t    if (!fgets(old_line, buffer_size, fp_target) && ferror(fp_target))\n"
        "\t\tERROR_EXIT(ptarget);",
        "BusyBox split-include read result",
    ),
    (
        "trunk/user/busybox/busybox-1.24.x/scripts/kconfig/conf.c",
        "\tcase ask_all:\n\t\tfflush(stdout);\n\t\tfgets(line, 128, stdin);\n\t\treturn;",
        "\tcase ask_all:\n\t\tfflush(stdout);\n"
        "\t\tif (!fgets(line, 128, stdin))\n\t\t\texit(1);\n\t\treturn;",
        "BusyBox Kconfig value read result",
    ),
    (
        "trunk/user/busybox/busybox-1.24.x/scripts/kconfig/conf.c",
        "\t\tcase ask_all:\n\t\t\tfflush(stdout);\n"
        "\t\t\tfgets(line, 128, stdin);\n\t\t\tstrip(line);",
        "\t\tcase ask_all:\n\t\t\tfflush(stdout);\n"
        "\t\t\tif (!fgets(line, 128, stdin))\n\t\t\t\texit(1);\n"
        "\t\t\tstrip(line);",
        "BusyBox Kconfig choice read result",
    ),
    (
        "trunk/user/busybox/busybox-1.24.x/scripts/kconfig/mconf.c",
        "\tpipe(pipefd);",
        "\tif (pipe(pipefd))\n\t\t_exit(EXIT_FAILURE);",
        "BusyBox menuconfig pipe result",
    ),
    (
        "trunk/user/busybox/busybox-1.24.x/scripts/kconfig/mconf.c",
        "static void show_textbox(const char *title, const char *text, int r, int c)\n"
        "{\n\tint fd;\n\n\tfd = creat(\".help.tmp\", 0777);\n"
        "\twrite(fd, text, strlen(text));",
        "static void show_textbox(const char *title, const char *text, int r, int c)\n"
        "{\n\tint fd;\n\tint len = strlen(text);\n\n"
        "\tfd = creat(\".help.tmp\", 0777);\n"
        "\tif (write(fd, text, len) != len)\n\t\texit(1);",
        "BusyBox menuconfig help write result",
    ),
    (
        "trunk/user/busybox/busybox-1.24.x/applets/usage.c",
        "\tfor (i = 0; i < num_messages; i++)\n"
        "\t\twrite(STDOUT_FILENO, usage_array[i].usage, "
        "strlen(usage_array[i].usage) + 1);",
        "\tfor (i = 0; i < num_messages; i++) {\n"
        "\t\tsize_t len = strlen(usage_array[i].usage) + 1;\n\n"
        "\t\tif (write(STDOUT_FILENO, usage_array[i].usage, len) != "
        "(ssize_t)len)\n\t\t\treturn 1;\n\t}",
        "BusyBox usage data write result",
    ),
    (
        "trunk/user/busybox/busybox-1.24.x/applets/applet_tables.c",
        "\tif (argv[2]) {\n"
        "\t\tchar line_old[80];\n"
        "\t\tchar line_new[80];\n"
        "\t\tFILE *fp;\n\n"
        "\t\tline_old[0] = 0;\n"
        "\t\tfp = fopen(argv[2], \"r\");\n"
        "\t\tif (fp) {\n"
        "\t\t\tfgets(line_old, sizeof(line_old), fp);\n"
        "\t\t\tfclose(fp);\n"
        "\t\t}\n"
        "\t\tsprintf(line_new, \"#define NUM_APPLETS %u\\n\", NUM_APPLETS);\n"
        "\t\tif (strcmp(line_old, line_new) != 0) {\n"
        "\t\t\tfp = fopen(argv[2], \"w\");\n"
        "\t\t\tif (!fp)\n"
        "\t\t\t\treturn 1;\n"
        "\t\t\tfputs(line_new, fp);\n"
        "\t\t}\n"
        "\t}\n\n"
        "\treturn 0;\n}",
        "\tif (argv[2]) {\n"
        "\t\tchar line_old[80];\n"
        "\t\tchar line_new[80];\n"
        "\t\tFILE *fp;\n\n"
        "\t\tline_old[0] = 0;\n"
        "\t\tfp = fopen(argv[2], \"r\");\n"
        "\t\tif (fp) {\n"
        "\t\t\tif (!fgets(line_old, sizeof(line_old), fp) && ferror(fp)) {\n"
        "\t\t\t\tfclose(fp);\n"
        "\t\t\t\treturn 1;\n"
        "\t\t\t}\n"
        "\t\t\tif (fclose(fp) != 0)\n"
        "\t\t\t\treturn 1;\n"
        "\t\t}\n"
        "\t\tsprintf(line_new, \"#define NUM_APPLETS %u\\n\", NUM_APPLETS);\n"
        "\t\tif (strcmp(line_old, line_new) != 0) {\n"
        "\t\t\tfp = fopen(argv[2], \"w\");\n"
        "\t\t\tif (!fp)\n"
        "\t\t\t\treturn 1;\n"
        "\t\t\tif (fputs(line_new, fp) < 0) {\n"
        "\t\t\t\tfclose(fp);\n"
        "\t\t\t\treturn 1;\n"
        "\t\t\t}\n"
        "\t\t\tif (fclose(fp) != 0)\n"
        "\t\t\t\treturn 1;\n"
        "\t\t}\n"
        "\t}\n\n"
        "\tif (fclose(stdout) != 0)\n"
        "\t\treturn 1;\n"
        "\treturn 0;\n}",
        "BusyBox applet table I/O results",
    ),
)
IMAGE_BUILD_SOURCE_PATCHES = (
    (
        "trunk/tools/mksquashfs_xz/squashfs-4.3/mksquashfs.c",
        "long long global_uid = -1, global_gid = -1;\n\n"
        "/* superblock attributes */",
        "long long global_uid = -1, global_gid = -1;\n\n"
        "static time_t reproducible_time(void)\n"
        "{\n"
        "\tconst char *value = getenv(\"SOURCE_DATE_EPOCH\");\n"
        "\tchar *end;\n"
        "\tunsigned long epoch;\n\n"
        "\tif (value == NULL || *value == '\\0')\n"
        "\t\treturn time(NULL);\n"
        "\terrno = 0;\n"
        "\tepoch = strtoul(value, &end, 10);\n"
        "\tif (errno != 0 || *end != '\\0' || epoch == 0) {\n"
        "\t\tfprintf(stderr, \"Invalid SOURCE_DATE_EPOCH\\n\");\n"
        "\t\texit(1);\n"
        "\t}\n"
        "\treturn (time_t) epoch;\n"
        "}\n\n"
        "/* superblock attributes */",
        "SquashFS reproducible timestamp helper",
    ),
    (
        "trunk/tools/mksquashfs_xz/squashfs-4.3/mksquashfs.c",
        "\tbase->mtime = buf->st_mtime;",
        "\tbase->mtime = reproducible_time();",
        "SquashFS inode timestamps",
    ),
    (
        "trunk/tools/mksquashfs_xz/squashfs-4.3/mksquashfs.c",
        "\t\tbuf.st_uid = getuid();\n"
        "\t\tbuf.st_gid = getgid();\n"
        "\t\tbuf.st_mtime = time(NULL);\n"
        "\t\tbuf.st_dev = 0;",
        "\t\tbuf.st_uid = getuid();\n"
        "\t\tbuf.st_gid = getgid();\n"
        "\t\tbuf.st_mtime = reproducible_time();\n"
        "\t\tbuf.st_dev = 0;",
        "SquashFS synthetic root timestamp",
    ),
    (
        "trunk/tools/mksquashfs_xz/squashfs-4.3/mksquashfs.c",
        "\t\tbuf.st_rdev = makedev(pseudo_ent->dev->major,\n"
        "\t\t\tpseudo_ent->dev->minor);\n"
        "\t\tbuf.st_mtime = time(NULL);\n"
        "\t\tbuf.st_ino = pseudo_ino ++;",
        "\t\tbuf.st_rdev = makedev(pseudo_ent->dev->major,\n"
        "\t\t\tpseudo_ent->dev->minor);\n"
        "\t\tbuf.st_mtime = reproducible_time();\n"
        "\t\tbuf.st_ino = pseudo_ino ++;",
        "SquashFS pseudo-entry timestamp",
    ),
    (
        "trunk/tools/mksquashfs_xz/squashfs-4.3/mksquashfs.c",
        "\tsBlk.mkfs_time = time(NULL);",
        "\tsBlk.mkfs_time = reproducible_time();",
        "SquashFS superblock timestamp",
    ),
    (
        "trunk/vendors/Ralink/Makefile",
        "$(ROOTDIR)/tools/mksquashfs_xz/mksquashfs $(ROMFSDIR) $(RAMDISK) -all-root -no-exports -noappend -nopad -noI -no-xattrs",
        "$(ROOTDIR)/tools/mksquashfs_xz/mksquashfs $(ROMFSDIR) $(RAMDISK) -all-root -no-exports -noappend -nopad -noI -no-xattrs -processors 1",
        "deterministic SquashFS processor count",
    ),
    (
        "trunk/user/busybox/busybox-1.24.x/scripts/kconfig/confdata.c",
        "\tsym = sym_lookup(\"KERNELVERSION\", 0);\n"
        "\tsym_calc_value(sym);\n"
        "\ttime(&now);\n"
        "\tenv = getenv(\"KCONFIG_NOTIMESTAMP\");",
        "\tsym = sym_lookup(\"KERNELVERSION\", 0);\n"
        "\tsym_calc_value(sym);\n"
        "\tenv = getenv(\"SOURCE_DATE_EPOCH\");\n"
        "\tif (env && *env) {\n"
        "\t\tchar *end;\n"
        "\t\tunsigned long epoch = strtoul(env, &end, 10);\n\n"
        "\t\tif (*end != '\\0' || epoch == 0)\n"
        "\t\t\treturn 1;\n"
        "\t\tnow = (time_t)epoch;\n"
        "\t} else {\n"
        "\t\ttime(&now);\n"
        "\t}\n"
        "\tenv = getenv(\"KCONFIG_NOTIMESTAMP\");",
        "BusyBox timestamp source epoch",
    ),
    (
        "trunk/user/busybox/busybox-1.24.x/scripts/kconfig/confdata.c",
        "\t\t\t\tstrftime(buf, sizeof(buf), \"#define AUTOCONF_TIMESTAMP \"\n"
        "\t\t\t\t\t\"\\\"%Y-%m-%d %H:%M:%S %Z\\\"\\n\", localtime(&now));\n"
        "\t\t\t/* if user has Factory timezone or some other odd install, the\n"
        "\t\t\t * %Z above will overflow the string leaving us with undefined\n"
        "\t\t\t * results ... so let's try again without the timezone.\n"
        "\t\t\t */\n"
        "\t\t\tif (ret == 0)\n"
        "\t\t\t\tstrftime(buf, sizeof(buf), \"#define AUTOCONF_TIMESTAMP \"\n"
        "\t\t\t\t\t\"\\\"%Y-%m-%d %H:%M:%S\\\"\\n\", localtime(&now));",
        "\t\t\t\tstrftime(buf, sizeof(buf), \"#define AUTOCONF_TIMESTAMP \"\n"
        "\t\t\t\t\t\"\\\"%Y-%m-%d %H:%M:%S UTC\\\"\\n\", gmtime(&now));\n"
        "\t\t\tif (ret == 0)\n"
        "\t\t\t\treturn 1;",
        "BusyBox timestamp UTC format",
    ),
    (
        "trunk/user/busybox/busybox-1.24.x/applets/usage_pod.c",
        "\t\tprintf(usage_array[i].aname);",
        "\t\tprintf(\"%s\", usage_array[i].aname);",
        "BusyBox usage POD literal format",
    ),
    (
        "trunk/tools/lzma/lzma-4.65/CPP/Common/MyCom.h",
        "STDMETHOD_(ULONG, Release)() { if (--__m_RefCount != 0)  "
        + chr(92)
        + "\n"
        "  return __m_RefCount; delete this; return 0; }",
        "STDMETHOD_(ULONG, Release)() { if (--__m_RefCount != 0) { "
        + chr(92)
        + "\n"
        "  return __m_RefCount; } delete this; return 0; }",
        "LZMA reference-count release scope",
    ),
    (
        "trunk/tools/lzma/lzma-4.65/CPP/Common/MyString.h",
        "    for (int i = 0; i < _length; i++)\n"
        "      if (s.Find(_chars[i]) >= 0)\n"
        "        return i;\n"
        "      return -1;",
        "    for (int i = 0; i < _length; i++)\n"
        "    {\n"
        "      if (s.Find(_chars[i]) >= 0)\n"
        "        return i;\n"
        "    }\n"
        "    return -1;",
        "LZMA string search loop scope",
    ),
    (
        "trunk/tools/lzma/lzma-4.65/CPP/7zip/Compress/LzmaEncoder.cpp",
        "      case NCoderPropID::kNumFastBytes:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG; props.fb = prop.ulVal; break;\n"
        "      case NCoderPropID::kMatchFinderCycles:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG; props.mc = prop.ulVal; break;\n"
        "      case NCoderPropID::kAlgorithm:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG; props.algo = prop.ulVal; break;\n"
        "      case NCoderPropID::kDictionarySize:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG; props.dictSize = prop.ulVal; break;\n"
        "      case NCoderPropID::kPosStateBits:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG; props.pb = prop.ulVal; break;\n"
        "      case NCoderPropID::kLitPosBits:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG; props.lp = prop.ulVal; break;\n"
        "      case NCoderPropID::kLitContextBits:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG; props.lc = prop.ulVal; break;\n"
        "      case NCoderPropID::kNumThreads:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG; props.numThreads = prop.ulVal; break;\n"
        "      case NCoderPropID::kMultiThread:\n"
        "        if (prop.vt != VT_BOOL) return E_INVALIDARG; props.numThreads = "
        "((prop.boolVal == VARIANT_TRUE) ? 2 : 1); break;\n"
        "      case NCoderPropID::kEndMarker:\n"
        "        if (prop.vt != VT_BOOL) return E_INVALIDARG; props.writeEndMark = "
        "(prop.boolVal == VARIANT_TRUE); break;\n"
        "      case NCoderPropID::kMatchFinder:\n"
        "        if (prop.vt != VT_BSTR) return E_INVALIDARG;\n"
        "        if (!ParseMatchFinder(prop.bstrVal, &props.btMode, &props.numHashBytes "
        "/* , &_matchFinderBase.skipModeBits */))\n"
        "          return E_INVALIDARG; break;",
        "      case NCoderPropID::kNumFastBytes:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG;\n"
        "        props.fb = prop.ulVal; break;\n"
        "      case NCoderPropID::kMatchFinderCycles:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG;\n"
        "        props.mc = prop.ulVal; break;\n"
        "      case NCoderPropID::kAlgorithm:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG;\n"
        "        props.algo = prop.ulVal; break;\n"
        "      case NCoderPropID::kDictionarySize:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG;\n"
        "        props.dictSize = prop.ulVal; break;\n"
        "      case NCoderPropID::kPosStateBits:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG;\n"
        "        props.pb = prop.ulVal; break;\n"
        "      case NCoderPropID::kLitPosBits:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG;\n"
        "        props.lp = prop.ulVal; break;\n"
        "      case NCoderPropID::kLitContextBits:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG;\n"
        "        props.lc = prop.ulVal; break;\n"
        "      case NCoderPropID::kNumThreads:\n"
        "        if (prop.vt != VT_UI4) return E_INVALIDARG;\n"
        "        props.numThreads = prop.ulVal; break;\n"
        "      case NCoderPropID::kMultiThread:\n"
        "        if (prop.vt != VT_BOOL) return E_INVALIDARG;\n"
        "        props.numThreads = ((prop.boolVal == VARIANT_TRUE) ? 2 : 1); break;\n"
        "      case NCoderPropID::kEndMarker:\n"
        "        if (prop.vt != VT_BOOL) return E_INVALIDARG;\n"
        "        props.writeEndMark = (prop.boolVal == VARIANT_TRUE); break;\n"
        "      case NCoderPropID::kMatchFinder:\n"
        "        if (prop.vt != VT_BSTR) return E_INVALIDARG;\n"
        "        if (!ParseMatchFinder(prop.bstrVal, &props.btMode, &props.numHashBytes "
        "/* , &_matchFinderBase.skipModeBits */))\n"
        "          return E_INVALIDARG;\n"
        "        break;",
        "LZMA encoder property control flow",
    ),
    (
        "trunk/tools/lzma/lzma-4.65/CPP/7zip/Compress/LZMA_Alone/LzmaBenchCon.cpp",
        "    UInt64 rating = GetDecompressRating(info.GlobalTime, info.GlobalFreq, "
        "info.UnpackSize, info.PackSize, info.NumIterations);\n"
        "    fprintf(f, kSep);",
        "    UInt64 rating = GetDecompressRating(info.GlobalTime, info.GlobalFreq, "
        "info.UnpackSize, info.PackSize, info.NumIterations);\n"
        "    fprintf(f, \"%s\", kSep);",
        "LZMA benchmark result separator format",
    ),
    (
        "trunk/tools/lzma/lzma-4.65/CPP/7zip/Compress/LZMA_Alone/LzmaBenchCon.cpp",
        "    fprintf(f, \"   Speed Usage    R/U Rating\");\n"
        "    if (j == 0)\n"
        "      fprintf(f, kSep);",
        "    fprintf(f, \"   Speed Usage    R/U Rating\");\n"
        "    if (j == 0)\n"
        "      fprintf(f, \"%s\", kSep);",
        "LZMA benchmark compression separator format",
    ),
    (
        "trunk/tools/lzma/lzma-4.65/CPP/7zip/Compress/LZMA_Alone/LzmaBenchCon.cpp",
        "    fprintf(f, \"    KB/s     %%   MIPS   MIPS\");\n"
        "    if (j == 0)\n"
        "      fprintf(f, kSep);",
        "    fprintf(f, \"    KB/s     %%   MIPS   MIPS\");\n"
        "    if (j == 0)\n"
        "      fprintf(f, \"%s\", kSep);",
        "LZMA benchmark decompression separator format",
    ),
    (
        "trunk/tools/lzma/lzma-4.65/CPP/7zip/Compress/LZMA_Alone/LzmaAlone.cpp",
        "        fprintf(stderr, kWriteError);",
        "        fprintf(stderr, \"%s\", kWriteError);",
        "LZMA write error literal format",
    ),
    (
        "trunk/tools/lzma/lzma-4.65/CPP/7zip/Compress/LZMA_Alone/LzmaAlone.cpp",
        "      fprintf(stderr, kReadError);",
        "      fprintf(stderr, \"%s\", kReadError);",
        "LZMA read error literal format",
    ),
    (
        "trunk/tools/lzma/lzma-4.65/C/LzmaEnc.c",
        "  Bool btMode;\n"
        "  if (!RangeEnc_Alloc(&p->rc, alloc))\n"
        "    return SZ_ERROR_MEM;\n"
        "  btMode = (p->matchFinderBase.btMode != 0);\n"
        "  #ifdef COMPRESS_MF_MT\n"
        "  p->mtMode = (p->multiThread && !p->fastMode && btMode);\n"
        "  #endif",
        "  if (!RangeEnc_Alloc(&p->rc, alloc))\n"
        "    return SZ_ERROR_MEM;\n"
        "  #ifdef COMPRESS_MF_MT\n"
        "  {\n"
        "    Bool btMode = (p->matchFinderBase.btMode != 0);\n"
        "    p->mtMode = (p->multiThread && !p->fastMode && btMode);\n"
        "  }\n"
        "  #endif",
        "LZMA threaded match-finder mode scope",
    ),
)
CPU_SOURCE_PATCHES = (
    (
        "trunk/linux-3.4.x/arch/mips/rt2880/Kconfig",
        "config  RALINK_MT7621_PLL900\n"
        "\tbool \"Set MT7621 CPU clock to 900MHz (Override Uboot config)\"\n"
        "\tdepends on (RALINK_MT7621)\n"
        "\tdefault n",
        "config  RALINK_MT7621_PLL800\n"
        "\tbool \"Set MT7621 CPU clock to 800MHz (Override Uboot config)\"\n"
        "\tdepends on (RALINK_MT7621)\n"
        "\tdefault n\n\n"
        "config  RALINK_MT7621_PLL900\n"
        "\tbool \"Set MT7621 CPU clock to 900MHz (Override Uboot config)\"\n"
        "\tdepends on (RALINK_MT7621)\n"
        "\tdefault n\n\n"
        "config  RALINK_MT7621_PLL1000\n"
        "\tbool \"Set MT7621 CPU clock to 1000MHz (Override Uboot config)\"\n"
        "\tdepends on (RALINK_MT7621)\n"
        "\tdefault n",
        "MT7621 CPU frequency Kconfig",
    ),
    (
        "trunk/linux-3.4.x/arch/mips/rt2880/init.c",
        "#if defined(CONFIG_RALINK_MT7621_PLL900)\n"
        "\t\tif ((reg & 0xff) != 0xc2) {\n"
        "\t\t\treg &= ~(0xff);\n"
        "\t\t\treg |=  (0xc2);\n"
        "\t\t\t(*((volatile u32 *)(RALINK_MEMCTRL_BASE + 0x648))) = reg;\n"
        "\t\t\tudelay(10);\n"
        "\t\t}\n"
        "#endif",
        "#if defined(CONFIG_RALINK_MT7621_PLL800)\n"
        "#define MT7621_PLL_TARGET_MHZ 800\n"
        "#elif defined(CONFIG_RALINK_MT7621_PLL900)\n"
        "#define MT7621_PLL_TARGET_MHZ 900\n"
        "#elif defined(CONFIG_RALINK_MT7621_PLL1000)\n"
        "#define MT7621_PLL_TARGET_MHZ 1000\n"
        "#endif\n"
        "#ifdef MT7621_PLL_TARGET_MHZ\n"
        "\t\t{\n"
        "\t\t\tu32 pll_base = (xtal == 25) ? 25 : 20;\n"
        "\t\t\tu32 target_fbdiv = MT7621_PLL_TARGET_MHZ / pll_base;\n"
        "\t\t\tu32 target_pll = ((target_fbdiv - 1) << 4) | 0x2;\n\n"
        "\t\t\tif ((reg & 0x7ff) != target_pll) {\n"
        "\t\t\t\treg &= ~(0x7ff);\n"
        "\t\t\t\treg |= target_pll;\n"
        "\t\t\t\t(*((volatile u32 *)(RALINK_MEMCTRL_BASE + 0x648))) = reg;\n"
        "\t\t\t\tudelay(10);\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "#undef MT7621_PLL_TARGET_MHZ\n"
        "#endif",
        "MT7621 CPU PLL programming",
    ),
)
SOURCE_PATCHES = (
    USERLAND_SOURCE_PATCHES
    + WIRELESS_SOURCE_PATCHES
    + HOST_BUILD_SOURCE_PATCHES
    + IMAGE_BUILD_SOURCE_PATCHES
    + CPU_SOURCE_PATCHES
)
SMP_SOURCE_CHECKS = (
    ("trunk/user/rc/rc.c", "\tset_cpu_affinity(is_ap_mode);", "CPU affinity startup"),
    (
        "trunk/user/rc/smp.c",
        "\t{ GIC_IRQ_FE,    SMP_MASK_CPU1 },",
        "MT7621 frame-engine IRQ affinity",
    ),
    (
        "trunk/user/rc/smp.c",
        "\t{ GIC_IRQ_PCIE0, SMP_MASK_CPU2 },",
        "MT7621 PCIe0 IRQ affinity",
    ),
    (
        "trunk/user/rc/smp.c",
        "\t{ GIC_IRQ_PCIE1, SMP_MASK_CPU3 },",
        "MT7621 PCIe1 IRQ affinity",
    ),
    (
        "trunk/user/rc/smp.c",
        "\t\t\trps_queue_set(rps_iflist[j], last_cpu_mask);",
        "RPS queue policy",
    ),
    (
        "trunk/user/rc/smp.c",
        "\t\t\txps_queue_set(rps_iflist[j], last_cpu_mask);",
        "XPS queue policy",
    ),
)
HIGH_RISK_WARNING_PATTERNS = (
    ("implicit-function-declaration", re.compile(r"warning: implicit declaration of function")),
    (
        "string-literal-address-comparison",
        re.compile(r"warning: comparison with string literal results in unspecified behavior"),
    ),
    (
        "format-argument-type",
        re.compile(r"warning: format .* expects argument of type"),
    ),
    ("format-truncation", re.compile(r"warning: .*may be truncated")),
    ("always-true-address", re.compile(r"warning: the address of .* will always evaluate")),
    ("implicit-fallthrough", re.compile(r"warning: this statement may fall through")),
    (
        "array-bounds",
        re.compile(r"warning: .*(?:array subscript|array bounds).*\[-Warray-bounds"),
    ),
    (
        "overflow",
        re.compile(r"warning: .*\[-W(?:stringop-)?overflow(?:=)?\]"),
    ),
    ("uninitialized", re.compile(r"warning: .*uninitialized")),
    ("use-after-free", re.compile(r"warning: .*use-after-free")),
    ("null-dereference", re.compile(r"warning: .*null .*dereference")),
    ("incompatible-pointer-types", re.compile(r"warning: .*incompatible pointer type")),
    ("int-conversion", re.compile(r"warning: .*\[-Wint-conversion\]")),
    (
        "ignored-result",
        re.compile(r"warning: ignoring return value of .*warn_unused_result"),
    ),
    (
        "missing-return",
        re.compile(r"warning: control reaches end of non-void function"),
    ),
    (
        "format-security",
        re.compile(r"warning: format not a string literal.*\[-Wformat-security\]"),
    ),
    (
        "misleading-indentation",
        re.compile(r"warning: this '(?:if|for)' clause does not guard"),
    ),
    (
        "unused-but-set-variable",
        re.compile(r"warning: variable .* set but not used.*\[-Wunused-but-set-variable\]"),
    ),
    (
        "discarded-qualifiers",
        re.compile(r"warning: .* discards 'const' qualifier.*\[-Wdiscarded-qualifiers\]"),
    ),
    (
        "ambiguous-parentheses",
        re.compile(r"warning: suggest parentheses around .*\[-Wparentheses\]"),
    ),
    (
        "macro-redefinition",
        re.compile(r'warning: ".+" redefined'),
    ),
)
AUDITED_LEGACY_WARNING_PATTERNS = (
    (
        "build-system-deprecation",
        re.compile(
            r"^(?:configure\.(?:ac|in):\d+|aclocal\.m4:\d+|Makefile\.am:\d+|"
            r"automake|aclocal|autoheader): warning: (?:"
            r"The macro `[A-Z0-9_]+' is obsolete\.|"
            r"this file was generated for autoconf 2\.(?:63|69)\.|"
            r"autoconf input should be named 'configure\.ac', not 'configure\.in'|"
            r"AM_INIT_AUTOMAKE: two- and three-arguments forms are deprecated\."
            r"(?:  For more info, see:)?|"
            r"AC_OUTPUT should be used without arguments\.|"
            r"'AM_CONFIG_HEADER': this macro is obsolete\.|"
            r"name 'aux' is reserved on W32 and DOS platforms|"
            r"'INCLUDES' is the old name for 'AM_CPPFLAGS' \(or '\*_CPPFLAGS'\)"
            r")$"
        ),
        90,
    ),
    (
        "parser-generator-deprecation",
        re.compile(
            r"^emp_ematch\.y(?::\d+\.\d+-\d+)?: warning: (?:"
            r"deprecated directive: .+ \[-Wdeprecated\]|"
            r"fix-its can be applied\.  Rerun with option '--update'\. \[-Wother\]"
            r")$"
        ),
        3,
    ),
    (
        "kernel-user-header-marker",
        re.compile(
            r"^.*linux-3\.4\.x/include/linux/types\.h:13:2: warning: #warning "
            r'"Attempt to use kernel headers from user space, see '
            r'http://kernelnewbies\.org/KernelHeaders" \[-Wcpp\]$'
        ),
        4,
    ),
    (
        "compiler-inline-decision",
        re.compile(
            r"^(?:iwlist\.c:410:1: warning: inlining failed in call to "
            r"'iw_print_gen_ie': call is unlikely and code size would grow|"
            r"iwevent\.c:632:1: warning: inlining failed in call to "
            r"'handle_netlink_events\.isra\.1': --param large-stack-frame-growth "
            r"limit reached) \[-Winline\]$"
        ),
        3,
    ),
    (
        "flashcp-review-marker",
        re.compile(
            r'^misc-utils/flashcp\.c:257:2: warning: #warning "Check for smaller '
            r'erase regions" \[-Wcpp\]$'
        ),
        1,
    ),
    (
        "busybox-compile-assertion",
        re.compile(
            r"^util-linux/umount\.c:86:16: warning: typedef 'bug' locally defined "
            r"but not used \[-Wunused-local-typedefs\]$"
        ),
        1,
    ),
    (
        "libtool-relink",
        re.compile(r"^libtool: warning: relinking 'libblkid\.la'$"),
        1,
    ),
)


class FirmwareError(ValueError):
    """An input cannot produce a supported firmware bundle."""


def parse_profile(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise FirmwareError(f"{path}:{line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        if key in values:
            raise FirmwareError(f"{path}:{line_number}: duplicate key {key}")
        values[key] = value
    return values


def validate_profile(path: Path) -> dict[str, str]:
    values = parse_profile(path)
    if values.get("CONFIG_LINUXDIR") != "linux-3.4.x":
        raise FirmwareError("CONFIG_LINUXDIR must be linux-3.4.x")
    if values.get("CONFIG_FIRMWARE_PRODUCT_ID") != '"RM2100"':
        raise FirmwareError('CONFIG_FIRMWARE_PRODUCT_ID must be "RM2100"')
    unsupported = sorted(
        key for key, value in values.items() if value == "y" and key not in ALLOWED_ENABLED_OPTIONS
    )
    if unsupported:
        raise FirmwareError(f"unsupported enabled option: {', '.join(unsupported)}")
    for key, expected in REQUIRED_PROFILE_VALUES.items():
        if values.get(key) != expected:
            raise FirmwareError(f"{key} must be {expected}")
    invalid_cpu_options = [
        option
        for option in CPU_PROFILE_OPTIONS.values()
        if values.get(option) not in {"n", "y"}
    ]
    if invalid_cpu_options:
        raise FirmwareError(
            f"CPU frequency options must be n or y: {', '.join(invalid_cpu_options)}"
        )
    enabled_cpu_options = [
        option for option in CPU_PROFILE_OPTIONS.values() if values[option] == "y"
    ]
    if len(enabled_cpu_options) > 1:
        raise FirmwareError("CPU frequency options are mutually exclusive")
    return values


def cpu_frequency_from_profile(values: dict[str, str]) -> str:
    enabled = [
        frequency
        for frequency, option in CPU_PROFILE_OPTIONS.items()
        if values[option] == "y"
    ]
    return enabled[0] if enabled else "bootloader"


def configure_profile(source: Path, output: Path, cpu_frequency: str) -> None:
    validate_profile(source)
    if cpu_frequency not in CPU_FREQUENCIES:
        raise FirmwareError(
            f"CPU frequency must be one of: {', '.join(CPU_FREQUENCIES)}"
        )
    content = source.read_text(encoding="utf-8")
    for frequency, option in CPU_PROFILE_OPTIONS.items():
        pattern = re.compile(rf"^{re.escape(option)}=.*$", re.MULTILINE)
        value = "y" if cpu_frequency == frequency else "n"
        content, count = pattern.subn(f"{option}={value}", content)
        if count != 1:
            raise FirmwareError(f"expected exactly one {option}, found {count}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    validate_profile(output)


def load_lock(path: Path) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        source = document["source"]
        archives = document["archives"]
        if document["schema"] != 1 or not isinstance(source, dict) or not isinstance(archives, dict):
            raise KeyError("schema")
        if source["url"] != "https://github.com/hanwckf/rt-n56u.git":
            raise FirmwareError("Source Lock must use the hanwckf 3.4 repository")
        if not re.fullmatch(r"[0-9a-f]{40}", str(source["commit"])):
            raise FirmwareError("Source Lock commit must be a full lowercase Git SHA")
        if not isinstance(source["source_date_epoch"], int) or source["source_date_epoch"] <= 0:
            raise FirmwareError("Source Lock source_date_epoch must be a positive integer")
        for archive_name in ("toolchain", "openssl"):
            archive = archives[archive_name]
            if not isinstance(archive, dict) or not str(archive["url"]).startswith("https://"):
                raise FirmwareError(f"Source Lock {archive_name} URL must use HTTPS")
            if not re.fullmatch(r"[0-9a-f]{64}", str(archive["sha256"])):
                raise FirmwareError(f"Source Lock {archive_name} SHA-256 is invalid")
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise FirmwareError(f"invalid Source Lock: {error}") from error
    if "4.4" in json.dumps(document, sort_keys=True):
        raise FirmwareError("Source Lock must not contain a 4.4 source")
    return document


def lock_value(path: Path, dotted_key: str) -> object:
    value: object = load_lock(path)
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise FirmwareError(f"Source Lock has no value for {dotted_key}")
        value = value[part]
    if isinstance(value, (dict, list)):
        raise FirmwareError(f"Source Lock value {dotted_key} is not scalar")
    return value


def read_secret(path: Path, label: str, minimum: int, maximum: int, forbidden: set[str]) -> str:
    value = path.read_text(encoding="utf-8").rstrip("\r\n")
    if value in forbidden:
        raise FirmwareError(f"{label} uses a forbidden universal default")
    if not minimum <= len(value) <= maximum:
        raise FirmwareError(f"{label} must contain {minimum}-{maximum} characters")
    if any(ord(character) < 33 or ord(character) > 126 for character in value):
        raise FirmwareError(f"{label} must contain printable ASCII without spaces")
    return value


def validate_credentials(admin_path: Path, wifi_path: Path) -> tuple[str, str]:
    admin_password = read_secret(
        admin_path, "administrator password", 5, 64, set()
    )
    wifi_password = read_secret(
        wifi_path, "Wi-Fi password", 8, 63, set()
    )
    if admin_password == wifi_password:
        raise FirmwareError("administrator password and Wi-Fi password must differ")
    return admin_password, wifi_password


def replace_c_define(content: str, name: str, value: str) -> str:
    pattern = re.compile(rf"^#define\s+{re.escape(name)}\s+.*$", re.MULTILINE)
    replacement = f"#define {name}\t{json.dumps(value)}"
    updated, count = pattern.subn(replacement, content)
    if count != 1:
        raise FirmwareError(f"expected exactly one C definition for {name}, found {count}")
    return updated


def replace_exact_once(content: str, old: str, new: str, label: str) -> str:
    count = content.count(old)
    if count != 1:
        raise FirmwareError(f"expected exactly one {label}, found {count}")
    return content.replace(old, new, 1)


def configure_kernel_cpu(source: Path, cpu_frequency: str) -> None:
    kernel_config = (
        source
        / "trunk"
        / "configs"
        / "boards"
        / "RM2100"
        / "kernel-3.4.x-5.0.config"
    )
    if not kernel_config.is_file():
        return

    content = kernel_config.read_text(encoding="utf-8")
    legacy_option = "# CONFIG_RALINK_MT7621_PLL900 is not set"
    if not all(option in content for option in KERNEL_CPU_OPTIONS.values()):
        expanded_options = "\n".join(
            f"# {option} is not set" for option in KERNEL_CPU_OPTIONS.values()
        )
        content = replace_exact_once(
            content,
            legacy_option,
            expanded_options,
            "RM2100 CPU PLL kernel options",
        )

    for frequency, option in KERNEL_CPU_OPTIONS.items():
        pattern = re.compile(
            rf"^(?:# {re.escape(option)} is not set|{re.escape(option)}=[yn])$",
            re.MULTILINE,
        )
        replacement = (
            f"{option}=y"
            if cpu_frequency == frequency
            else f"# {option} is not set"
        )
        content, count = pattern.subn(replacement, content)
        if count != 1:
            raise FirmwareError(f"expected exactly one {option}, found {count}")

    kernel_config.write_text(content, encoding="utf-8", newline="\n")


def prepare_source(
    source: Path, profile: Path, admin_password_file: Path, wifi_password_file: Path
) -> None:
    profile_values = validate_profile(profile)
    admin_password, wifi_password = validate_credentials(
        admin_password_file, wifi_password_file
    )

    template = source / "trunk" / "configs" / "templates" / "RM2100.config"
    defaults = source / "trunk" / "user" / "shared" / "defaults.h"
    if not template.is_file() or not defaults.is_file():
        raise FirmwareError(f"source tree is not a supported RM2100 checkout: {source}")

    shutil.copyfile(profile, template)
    defaults_content = defaults.read_text(encoding="utf-8")
    defaults_content = replace_c_define(
        defaults_content, "DEF_ROOT_PASSWORD", admin_password
    )
    country_code = profile_values["CONFIG_FIRMWARE_WLAN_COUNTRY_CODE"].strip('"')
    defaults_content = replace_c_define(defaults_content, "DEF_WLAN_2G_CC", country_code)
    defaults_content = replace_c_define(defaults_content, "DEF_WLAN_5G_CC", country_code)
    defaults_content = replace_c_define(defaults_content, "DEF_WLAN_2G_PSK", wifi_password)
    defaults_content = replace_c_define(defaults_content, "DEF_WLAN_5G_PSK", wifi_password)
    defaults.write_text(defaults_content, encoding="utf-8", newline="\n")

    runtime_defaults = source / "trunk" / "user" / "shared" / "defaults.c"
    if runtime_defaults.is_file():
        runtime_content = runtime_defaults.read_text(encoding="utf-8")
        runtime_content = replace_exact_once(
            runtime_content,
            '{ "http_access", "0" }',
            '{ "http_access", "2" }',
            "http_access default",
        )
        runtime_content = replace_exact_once(
            runtime_content,
            '{ "http_proto", "0" }',
            '{ "http_proto", "1" }',
            "http_proto default",
        )
        runtime_content = replace_exact_once(
            runtime_content,
            '{ "sshd_enable", "1" }',
            '{ "sshd_enable", "0" }',
            "sshd_enable default",
        )
        runtime_content = replace_exact_once(
            runtime_content,
            SFE_DEFAULT_DISABLED,
            SFE_DEFAULT_ENABLED,
            "SFE runtime default",
        )
        runtime_defaults.write_text(runtime_content, encoding="utf-8", newline="\n")

    runtime_network = source / "trunk" / "user" / "rc" / "net.c"
    if runtime_network.is_file():
        network_content = runtime_network.read_text(encoding="utf-8")
        network_content = replace_exact_once(
            network_content,
            SFE_RUNTIME_ORIGINAL,
            SFE_RUNTIME_HARDENED,
            "SFE runtime state handling",
        )
        runtime_network.write_text(network_content, encoding="utf-8", newline="\n")

    for relative_path, old, new, label in SOURCE_PATCHES:
        source_file = source / relative_path
        if not source_file.is_file():
            continue
        source_content = source_file.read_text(encoding="utf-8")
        source_content = replace_exact_once(source_content, old, new, label)
        source_file.write_text(source_content, encoding="utf-8", newline="\n")

    configure_kernel_cpu(source, cpu_frequency_from_profile(profile_values))

    xz_makefile = source / "trunk" / "tools" / "mksquashfs_xz" / "Makefile"
    if xz_makefile.is_file():
        xz_content = xz_makefile.read_text(encoding="utf-8")
        xz_content = replace_exact_once(
            xz_content,
            "build_xz:\n\tmake -C $(SRC_NAME2)",
            "build_xz:\n\tsed -i 's/ po / /g' $(SRC_NAME2)/Makefile\n\tmake -C $(SRC_NAME2)",
            "xz build recipe",
        )
        xz_makefile.write_text(xz_content, encoding="utf-8", newline="\n")

    mkimage = source / "trunk" / "tools" / "mkimage" / "mkimage.c"
    if mkimage.is_file():
        mkimage_content = mkimage.read_text(encoding="utf-8")
        mkimage_content = replace_exact_once(
            mkimage_content,
            "hdr->ih_time  = htonl(sbuf.st_mtime);",
            'hdr->ih_time  = htonl(getenv("SOURCE_DATE_EPOCH") '
            '? strtoul(getenv("SOURCE_DATE_EPOCH"), NULL, 10) : sbuf.st_mtime);',
            "mkimage timestamp assignment",
        )
        mkimage_content = replace_exact_once(
            mkimage_content,
            '\t\t\t\tsscanf(argv[1], "%d.%d", &tail_pre.kernel.major, '
            "&tail_pre.kernel.minor);",
            '\t\t\t\tif (sscanf(argv[1], "%hhu.%hhu", &tail_pre.kernel.major, '
            "&tail_pre.kernel.minor) != 2)\n\t\t\t\t\tusage ();",
            "mkimage kernel version parser",
        )
        mkimage_content = replace_exact_once(
            mkimage_content,
            '\t\t\t\tsscanf(argv[2], "%d.%d%c", &tail_pre.fs.major, '
            "&tail_pre.fs.minor, &tail_pre.sub_fs);   ",
            '\t\t\t\tif (sscanf(argv[2], "%hhu.%hhu%c", &tail_pre.fs.major, '
            "&tail_pre.fs.minor, &tail_pre.sub_fs) < 2)\n\t\t\t\t\tusage ();",
            "mkimage filesystem version parser",
        )
        mkimage.write_text(mkimage_content, encoding="utf-8", newline="\n")

    openssl_makefile = source / "trunk" / "libs" / "libssl" / "Makefile"
    if openssl_makefile.is_file():
        openssl_content = openssl_makefile.read_text(encoding="utf-8")
        openssl_content = replace_exact_once(
            openssl_content,
            "SRC_NAME=openssl-1.1.1k",
            "SRC_NAME=openssl-1.1.1w",
            "OpenSSL source version",
        )
        openssl_content = replace_exact_once(
            openssl_content,
            "SRC_URL=https://www.openssl.org/source/$(SRC_NAME).tar.gz",
            "SRC_URL=https://github.com/openssl/openssl/releases/download/OpenSSL_1_1_1w/$(SRC_NAME).tar.gz",
            "OpenSSL source URL",
        )
        openssl_content = replace_exact_once(
            openssl_content,
            "download_test:\n"
            "\t( if [ ! -f $(SRC_NAME).tar.gz ]; then \\\n"
            "\t\twget -t5 --timeout=20 --no-check-certificate -O $(SRC_NAME).tar.gz $(SRC_URL); \\\n"
            "\tfi )",
            "download_test:\n\ttest -f $(SRC_NAME).tar.gz",
            "OpenSSL download recipe",
        )
        openssl_content = replace_exact_once(
            openssl_content,
            "\t\ttar -xf $(SRC_NAME).tar.gz; \\\n\t\tpatch -d $(SRC_NAME) -p1 < $(SRC_NAME).patch; \\\n",
            "\t\ttar -xf $(SRC_NAME).tar.gz; \\\n",
            "OpenSSL extraction patch recipe",
        )
        openssl_makefile.write_text(openssl_content, encoding="utf-8", newline="\n")


def verify_source_policy(source: Path, report: Path) -> dict[str, object]:
    runtime_defaults = source / "trunk" / "user" / "shared" / "defaults.c"
    runtime_network = source / "trunk" / "user" / "rc" / "net.c"
    if not runtime_defaults.is_file() or not runtime_network.is_file():
        raise FirmwareError("prepared source is missing the RM2100 runtime policy files")

    defaults_content = runtime_defaults.read_text(encoding="utf-8")
    network_content = runtime_network.read_text(encoding="utf-8")
    checks = {
        "SFE default mode": defaults_content.count(SFE_DEFAULT_ENABLED) == 1
        and SFE_DEFAULT_DISABLED not in defaults_content,
        "CPU watchdog default": defaults_content.count('\t{ "watchdog_cpu", "1" },') == 1,
        "SFE module state handling": network_content.count(SFE_RUNTIME_HARDENED) == 1
        and SFE_RUNTIME_ORIGINAL not in network_content,
    }
    source_cache: dict[str, str] = {}
    for relative_path, old, new, label in SOURCE_PATCHES:
        source_file = source / relative_path
        if relative_path not in source_cache:
            source_cache[relative_path] = (
                source_file.read_text(encoding="utf-8") if source_file.is_file() else ""
            )
        content = source_cache[relative_path]
        checks[label] = content.count(new) == 1 and (old in new or old not in content)
    for relative_path, snippet, label in SMP_SOURCE_CHECKS:
        source_file = source / relative_path
        if relative_path not in source_cache:
            source_cache[relative_path] = (
                source_file.read_text(encoding="utf-8") if source_file.is_file() else ""
            )
        checks[label] = source_cache[relative_path].count(snippet) == 1

    template = source / "trunk" / "configs" / "templates" / "RM2100.config"
    kernel_config = (
        source
        / "trunk"
        / "configs"
        / "boards"
        / "RM2100"
        / "kernel-3.4.x-5.0.config"
    )
    if not template.is_file() or not kernel_config.is_file():
        raise FirmwareError("prepared source is missing the RM2100 CPU policy files")
    cpu_selection = cpu_frequency_from_profile(validate_profile(template))
    kernel_values = parse_kernel_config(kernel_config)
    for frequency, option in KERNEL_CPU_OPTIONS.items():
        expected_value = "y" if cpu_selection == frequency else "n"
        checks[f"{frequency} MHz kernel PLL selection"] = (
            kernel_values.get(option) == expected_value
        )

    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise FirmwareError(f"source policy failed: {', '.join(failed)}")

    document: dict[str, object] = {
        "schema": 1,
        "sfe": {
            "default_mode": 1,
            "bridge_ingress_bypass": False,
            "module_state_rechecked": True,
            "conntrack_fallback_on_load_failure": True,
        },
        "network_distribution": {
            "mt7621_irq_affinity_verified": True,
            "rps_xps_queue_policy_verified": True,
        },
        "cpu_frequency_policy": {
            "selection": cpu_selection,
            "forced_frequency_mhz": (
                None if cpu_selection == "bootloader" else int(cpu_selection)
            ),
            "supported_modes": list(CPU_FREQUENCIES),
            "exact_source_patches": len(CPU_SOURCE_PATCHES),
            "full_fbdiv_register_programming": True,
            "kernel_options_mutually_exclusive": True,
        },
        "userland_hardening": {
            "exact_source_patches": len(USERLAND_SOURCE_PATCHES),
            "bounded_pptp_interface_filter": True,
            "ctype_arguments_are_unsigned": True,
            "ascii_hex_length_scope_verified": True,
            "ebtables_counter_errors_propagated": True,
            "https_renegotiation_disabled_in_context": True,
            "implicit_function_declarations_removed": [
                "flash_mtd_read",
                "isdigit",
                "memset",
            ],
        },
        "wireless_hardening": {
            "driver": "mt7615-5.0.5.1",
            "exact_source_patches": len(WIRELESS_SOURCE_PATCHES),
            "spatial_stream_index_validated": True,
            "spatial_stream_range": [1, 4],
            "invalid_spatial_stream_fallback": 1,
        },
        "host_build_hardening": {
            "component": "busybox-1.24.x",
            "exact_source_patches": len(HOST_BUILD_SOURCE_PATCHES),
            "checked_io_results": ["fgets", "fputs", "pipe", "write", "fclose"],
            "generated_output_close_checked": True,
        },
        "image_build_hardening": {
            "components": ["busybox-1.24.x", "lzma-4.65"],
            "exact_source_patches": len(IMAGE_BUILD_SOURCE_PATCHES),
            "ambiguous_control_flow_removed": True,
            "busybox_timestamp_from_source_epoch": True,
            "busybox_timestamp_is_utc": True,
            "literal_format_strings": True,
            "lzma_string_search_checks_all_characters": True,
            "squashfs_timestamps_from_source_epoch": True,
        },
        "watchdog": {"default_enabled": True},
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return document


def verify_build_log(path: Path, report: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    warning_lines = [line for line in lines if "warning:" in line]
    category_counts = {
        name: sum(1 for line in warning_lines if pattern.search(line))
        for name, pattern in HIGH_RISK_WARNING_PATTERNS
    }
    failed = {name: count for name, count in category_counts.items() if count}
    if failed:
        summary = ", ".join(f"{name}={count}" for name, count in failed.items())
        raise FirmwareError(f"forbidden compiler warnings: {summary}")

    legacy_counts = {
        name: sum(1 for line in warning_lines if pattern.search(line))
        for name, pattern, _maximum in AUDITED_LEGACY_WARNING_PATTERNS
    }
    unexpected = [
        line
        for line in warning_lines
        if not any(pattern.search(line) for _, pattern, _ in AUDITED_LEGACY_WARNING_PATTERNS)
    ]
    if unexpected:
        examples = "; ".join(unexpected[:3])
        raise FirmwareError(
            f"unexpected compiler warnings: count={len(unexpected)}; {examples}"
        )
    legacy_limits = {
        name: maximum for name, _pattern, maximum in AUDITED_LEGACY_WARNING_PATTERNS
    }
    exceeded = {
        name: count
        for name, count in legacy_counts.items()
        if count > legacy_limits[name]
    }
    if exceeded:
        summary = ", ".join(
            f"{name}={count}>{legacy_limits[name]}" for name, count in exceeded.items()
        )
        raise FirmwareError(f"legacy compiler warning limits exceeded: {summary}")

    document: dict[str, object] = {
        "schema": 1,
        "total_warnings": len(warning_lines),
        "high_risk_warnings": 0,
        "legacy_warnings": len(warning_lines),
        "unknown_warnings": 0,
        "enforced_categories": category_counts,
        "audited_legacy_categories": legacy_counts,
        "audited_legacy_limits": legacy_limits,
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return document


def parse_kernel_config(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    unset_pattern = re.compile(r"^# (CONFIG_[A-Z0-9_]+) is not set$")
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        unset = unset_pattern.fullmatch(line)
        if unset:
            key, value = unset.group(1), "n"
        elif line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
        else:
            continue
        if key in values:
            raise FirmwareError(f"{path}:{line_number}: duplicate kernel option {key}")
        values[key] = value
    return values


def verify_kernel_config(
    path: Path, cpu_frequency: str, report: Path
) -> dict[str, object]:
    if cpu_frequency not in CPU_FREQUENCIES:
        raise FirmwareError(
            f"CPU frequency must be one of: {', '.join(CPU_FREQUENCIES)}"
        )
    values = parse_kernel_config(path)
    expected = dict(KERNEL_BASELINE)
    for frequency, option in KERNEL_CPU_OPTIONS.items():
        expected[option] = "y" if cpu_frequency == frequency else "n"
    failed = [
        f"{key}={expected_value} (found {values.get(key, 'missing')})"
        for key, expected_value in expected.items()
        if values.get(key) != expected_value
    ]
    if failed:
        raise FirmwareError(f"kernel performance baseline failed: {', '.join(failed)}")

    document: dict[str, object] = {
        "schema": 1,
        "kernel": "3.4",
        "cpu": {
            "selection": cpu_frequency,
            "forced_frequency_mhz": (
                None if cpu_frequency == "bootloader" else int(cpu_frequency)
            ),
            "logical_cpus": 4,
            "smp": True,
        },
        "scheduler": {"hz": 250, "preemption": "none"},
        "network_acceleration": {
            "sfe": True,
            "conntrack_events": True,
            "rps": True,
            "xps": True,
        },
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return document


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def firmware_bundle_files(bundle: Path, include_reproducibility: bool) -> list[str]:
    if not bundle.is_dir():
        raise FirmwareError(f"firmware bundle directory not found: {bundle}")
    images = sorted(path.name for path in bundle.glob("RM2100_3.4*.trx") if path.is_file())
    if len(images) != 1:
        raise FirmwareError(
            f"expected one RM2100 3.4 image in {bundle}, found {len(images)}"
        )
    files = [images[0], *BUNDLE_METADATA_FILES]
    if include_reproducibility:
        files.append(REPRODUCIBILITY_REPORT_FILE)
    return files


def verify_bundle_checksums(bundle: Path, expected_files: list[str]) -> None:
    checksum_path = bundle / BUNDLE_CHECKSUM_FILE
    if not checksum_path.is_file():
        raise FirmwareError(f"missing bundle checksum file: {checksum_path}")
    entries: dict[str, str] = {}
    for line in checksum_path.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\]+)", line)
        if not match or match.group(2) in entries:
            raise FirmwareError(f"invalid bundle checksum entry: {line}")
        entries[match.group(2)] = match.group(1)
    if set(entries) != set(expected_files):
        raise FirmwareError("bundle checksum inventory does not match expected files")
    for name, expected in entries.items():
        path = bundle / name
        if not path.is_file() or path.is_symlink():
            raise FirmwareError(f"invalid bundle file: {path}")
        if sha256_file(path) != expected:
            raise FirmwareError(f"bundle checksum mismatch: {name}")


def write_bundle_checksums(bundle: Path, files: list[str]) -> None:
    content = "".join(f"{sha256_file(bundle / name)}  {name}\n" for name in files)
    (bundle / BUNDLE_CHECKSUM_FILE).write_text(
        content, encoding="ascii", newline="\n"
    )


def verify_reproducibility(reference: Path, rebuild: Path) -> dict[str, object]:
    reference_files = firmware_bundle_files(reference, include_reproducibility=False)
    rebuild_files = firmware_bundle_files(rebuild, include_reproducibility=False)
    if reference_files != rebuild_files:
        raise FirmwareError("rebuild bundle inventory differs from reference")

    expected_inventory = set(reference_files) | {BUNDLE_CHECKSUM_FILE}
    for bundle in (reference, rebuild):
        actual_inventory = {path.name for path in bundle.iterdir()}
        if actual_inventory != expected_inventory:
            raise FirmwareError(f"unexpected firmware bundle inventory: {bundle}")
        verify_bundle_checksums(bundle, reference_files)

    differing = [
        name
        for name in sorted(expected_inventory)
        if (reference / name).read_bytes() != (rebuild / name).read_bytes()
    ]
    if differing:
        raise FirmwareError(
            "firmware rebuild is not byte-identical: " + ", ".join(differing)
        )

    try:
        manifest = json.loads(
            (reference / "manifest.json").read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise FirmwareError(f"invalid firmware manifest: {error}") from error
    if not isinstance(manifest, dict) or not isinstance(manifest.get("artifact"), dict):
        raise FirmwareError("invalid firmware manifest structure")
    image_name = reference_files[0]
    image_sha256 = sha256_file(reference / image_name)
    if manifest.get("artifact", {}).get("sha256") != image_sha256:
        raise FirmwareError("manifest firmware digest does not match rebuilt image")

    document: dict[str, object] = {
        "schema": 1,
        "builds_compared": 2,
        "byte_identical": True,
        "compared_files": sorted(expected_inventory),
        "image": {"filename": image_name, "sha256": image_sha256},
        "source": manifest.get("source"),
        "builder": manifest.get("builder"),
        "timestamp": manifest.get("artifact", {}).get("timestamp"),
    }
    report_content = json.dumps(document, indent=2, sort_keys=True) + "\n"
    for bundle in (reference, rebuild):
        (bundle / REPRODUCIBILITY_REPORT_FILE).write_text(
            report_content, encoding="utf-8", newline="\n"
        )
        final_files = firmware_bundle_files(bundle, include_reproducibility=True)
        write_bundle_checksums(bundle, final_files)
        verify_bundle_checksums(bundle, final_files)

    final_inventory = expected_inventory | {REPRODUCIBILITY_REPORT_FILE}
    if any(
        (reference / name).read_bytes() != (rebuild / name).read_bytes()
        for name in final_inventory
    ):
        raise FirmwareError("sealed reproducibility bundles differ")
    return document


def verify_image(
    image: Path,
    manifest: Path,
    profile: Path,
    source_commit: str,
    builder_commit: str,
    expected_timestamp: int,
) -> dict[str, object]:
    profile_values = validate_profile(profile)
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise FirmwareError("source commit must be a full lowercase Git SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", builder_commit):
        raise FirmwareError("builder commit must be a full lowercase Git SHA")

    content = image.read_bytes()
    if len(content) <= IMAGE_HEADER.size:
        raise FirmwareError("firmware image is too small")
    header = content[: IMAGE_HEADER.size]
    payload = content[IMAGE_HEADER.size :]
    (
        magic,
        header_crc,
        timestamp,
        data_size,
        load_address,
        entry_point,
        data_crc,
        operating_system,
        architecture,
        image_type,
        compression,
        tail,
        kernel_size,
    ) = IMAGE_HEADER.unpack(header)

    header_for_crc = header[:4] + b"\0\0\0\0" + header[8:]
    checks = {
        "magic": magic == IMAGE_MAGIC,
        "header CRC": zlib.crc32(header_for_crc) == header_crc,
        "data size": data_size == len(payload),
        "data CRC": zlib.crc32(payload) == data_crc,
        "firmware size": MIN_IMAGE_SIZE <= len(content) <= MAX_IMAGE_SIZE,
        "kernel size": 0 < kernel_size < data_size,
        "timestamp": timestamp == expected_timestamp,
        "Linux OS": operating_system == 5,
        "MIPS architecture": architecture == 5,
        "kernel image type": image_type == 2,
        "LZMA compression": compression == 3,
        "kernel version": tuple(tail[:2]) == (3, 4),
        "filesystem version": tuple(tail[2:4]) == (3, 9),
        "RM2100 product": tail[4:27].split(b"\0", 1)[0] == b"RM2100",
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise FirmwareError(f"firmware verification failed: {', '.join(failed)}")

    cpu_frequency = cpu_frequency_from_profile(profile_values)
    document: dict[str, object] = {
        "schema": 1,
        "device": "RM2100",
        "kernel": "3.4",
        "filesystem": "3.9",
        "source": {"commit": source_commit},
        "builder": {"commit": builder_commit},
        "profile": {"sha256": sha256_file(profile)},
        "cpu": {
            "selection": cpu_frequency,
            "forced_frequency_mhz": (
                None if cpu_frequency == "bootloader" else int(cpu_frequency)
            ),
        },
        "wireless": {
            "country_code": profile_values["CONFIG_FIRMWARE_WLAN_COUNTRY_CODE"].strip('"')
        },
        "artifact": {
            "filename": image.name,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "header_crc32": f"{header_crc:08x}",
            "data_crc32": f"{data_crc:08x}",
            "timestamp": timestamp,
            "created_utc": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
            "load_address": f"0x{load_address:08x}",
            "entry_point": f"0x{entry_point:08x}",
            "kernel_size": kernel_size,
        },
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-profile")
    validate.add_argument("profile", type=Path)

    configure = subparsers.add_parser("configure-profile")
    configure.add_argument("source", type=Path)
    configure.add_argument("output", type=Path)
    configure.add_argument("--cpu-frequency", required=True, choices=CPU_FREQUENCIES)

    credentials = subparsers.add_parser("validate-credentials")
    credentials.add_argument("admin_password_file", type=Path)
    credentials.add_argument("wifi_password_file", type=Path)

    prepare = subparsers.add_parser("prepare-source")
    prepare.add_argument("source", type=Path)
    prepare.add_argument("--profile", required=True, type=Path)
    prepare.add_argument("--admin-password-file", required=True, type=Path)
    prepare.add_argument("--wifi-password-file", required=True, type=Path)

    verify_source = subparsers.add_parser("verify-source-policy")
    verify_source.add_argument("source", type=Path)
    verify_source.add_argument("--report", required=True, type=Path)

    verify_warnings = subparsers.add_parser("verify-build-log")
    verify_warnings.add_argument("build_log", type=Path)
    verify_warnings.add_argument("--report", required=True, type=Path)

    verify = subparsers.add_parser("verify-image")
    verify.add_argument("image", type=Path)
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--profile", required=True, type=Path)
    verify.add_argument("--source-commit", required=True)
    verify.add_argument("--builder-commit", required=True)
    verify.add_argument("--expected-timestamp", required=True, type=int)

    verify_kernel = subparsers.add_parser("verify-kernel-config")
    verify_kernel.add_argument("kernel_config", type=Path)
    verify_kernel.add_argument("--cpu-frequency", required=True, choices=CPU_FREQUENCIES)
    verify_kernel.add_argument("--report", required=True, type=Path)

    verify_rebuild = subparsers.add_parser("verify-reproducibility")
    verify_rebuild.add_argument("reference", type=Path)
    verify_rebuild.add_argument("rebuild", type=Path)

    validate_lock = subparsers.add_parser("validate-lock")
    validate_lock.add_argument("lock", type=Path)

    read_lock = subparsers.add_parser("lock-value")
    read_lock.add_argument("lock", type=Path)
    read_lock.add_argument("key")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        if arguments.command == "validate-profile":
            validate_profile(arguments.profile)
            print(f"valid profile: {arguments.profile}")
            return 0
        if arguments.command == "validate-credentials":
            validate_credentials(arguments.admin_password_file, arguments.wifi_password_file)
            print("valid provisioning credentials")
            return 0
        if arguments.command == "configure-profile":
            configure_profile(arguments.source, arguments.output, arguments.cpu_frequency)
            print(f"configured profile: {arguments.output}")
            return 0
        if arguments.command == "prepare-source":
            prepare_source(
                arguments.source,
                arguments.profile,
                arguments.admin_password_file,
                arguments.wifi_password_file,
            )
            print(f"prepared source: {arguments.source}")
            return 0
        if arguments.command == "verify-image":
            verify_image(
                arguments.image,
                arguments.manifest,
                arguments.profile,
                arguments.source_commit,
                arguments.builder_commit,
                arguments.expected_timestamp,
            )
            print(f"verified firmware: {arguments.image}")
            return 0
        if arguments.command == "verify-source-policy":
            verify_source_policy(arguments.source, arguments.report)
            print(f"verified source policy: {arguments.source}")
            return 0
        if arguments.command == "verify-build-log":
            verify_build_log(arguments.build_log, arguments.report)
            print(f"verified compiler warning policy: {arguments.build_log}")
            return 0
        if arguments.command == "verify-kernel-config":
            verify_kernel_config(
                arguments.kernel_config, arguments.cpu_frequency, arguments.report
            )
            print(f"verified kernel config: {arguments.kernel_config}")
            return 0
        if arguments.command == "verify-reproducibility":
            verify_reproducibility(arguments.reference, arguments.rebuild)
            print(f"verified reproducible firmware bundle: {arguments.reference}")
            return 0
        if arguments.command == "validate-lock":
            load_lock(arguments.lock)
            print(f"valid Source Lock: {arguments.lock}")
            return 0
        if arguments.command == "lock-value":
            print(lock_value(arguments.lock, arguments.key))
            return 0
        raise FirmwareError(f"unknown command: {arguments.command}")
    except (FirmwareError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
