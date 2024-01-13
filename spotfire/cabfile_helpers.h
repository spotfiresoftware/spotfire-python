/* Copyright (c) 2023. Cloud Software Group, Inc.
   This file is subject to the license terms contained
   in the license file that is distributed with this file. */

#ifndef SPOTFIRE_CABFILE_HELPERS_H_
#define SPOTFIRE_CABFILE_HELPERS_H_

extern FNFCIALLOC(_fci_cb_alloc);
extern FNFCIFREE(_fci_cb_free);
extern FNFCIOPEN(_fci_cb_open);
extern FNFCIREAD(_fci_cb_read);
extern FNFCIWRITE(_fci_cb_write);
extern FNFCICLOSE(_fci_cb_close);
extern FNFCISEEK(_fci_cb_seek);
extern FNFCIDELETE(_fci_cb_delete);
extern FNFCIFILEPLACED(_fci_cb_file_placed);
extern FNFCIGETTEMPFILE(_fci_cb_get_temp_file);
extern FNFCISTATUS(_fci_cb_status);
extern FNFCIGETNEXTCABINET(_fci_cb_get_next_cabinet);
extern FNFCIGETOPENINFO(_fci_cb_get_open_info);

#endif /* SPOTFIRE_CABFILE_HELPERS_H_ */
